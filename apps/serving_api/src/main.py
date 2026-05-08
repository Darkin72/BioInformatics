"""Serving API with JWT authentication and role-based authorization."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import queue
import threading
import time
import uuid
from collections import Counter
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from apps.serving_api.src.cafa6_client import (
    Cafa6AnalysisError,
    Cafa6ValidationError,
    run_cafa6_analysis,
)
from libs.protein_rt.cassandra_store import CassandraStore
from libs.protein_rt.config import CassandraConfig

JWT_ALGORITHM = "HS256"
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
JWT_EXPIRES_SECONDS = int(os.getenv("JWT_EXPIRES_SECONDS", "3600"))
APP_TIMEZONE = timezone(timedelta(hours=7))

Role = str


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class UserPublic(BaseModel):
    username: str
    display_name: str
    roles: list[Role]


class AdminUserItem(BaseModel):
    username: str
    roles: list[Role]
    is_admin: bool


class AdminUserList(BaseModel):
    items: list[AdminUserItem]
    returned: int
    updated_at: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic


class CreateInferenceRequestPayload(BaseModel):
    protein_id: str
    sequence: str
    source: str
    metadata: dict[str, Any] | None = None


class RequestInput(BaseModel):
    protein_id: str
    sequence: str | None = None
    sequence_length: int | None = None
    source: str | None = None
    metadata: dict[str, Any] | None = None


class InferenceRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    request_id: str
    protein_id: str
    username: str | None = None
    source: str | None = None
    created_at: str
    updated_at: str | None = None
    current_status: str
    stage_name: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retry_count: int | None = None
    model_version: str | None = None
    feature_version: str | None = None


class PredictionTerm(BaseModel):
    term_id: str
    term_name: str | None = None
    ontology: str | None = None
    score: float
    definition: str | None = None


class LatestPrediction(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    protein_id: str
    request_id: str
    predicted_at: str
    model_version: str
    top_terms: list[PredictionTerm]
    confidence_summary: str | None = None
    server_result: dict[str, Any] | None = None


class RequestResult(BaseModel):
    request: InferenceRequest
    input: RequestInput | None = None
    prediction: LatestPrediction | None = None
    server_result: dict[str, Any] | None = None


class PipelineMetricPoint(BaseModel):
    window_start: str
    window_end: str
    metric_name: str
    metric_value: int | float
    tags: dict[str, str] | None = None


class DashboardSummary(BaseModel):
    total_today: int
    status_counts: dict[str, int]
    avg_latency_ms: int
    p95_latency_ms: int
    error_rate: float
    throughput: list[PipelineMetricPoint]
    recent_requests: list[InferenceRequest]
    recent_predictions: list[LatestPrediction]
    recent_failed_requests: list[InferenceRequest]
    error_counts: dict[str, int]
    cassandra_query_patterns: list[str]
    cassandra_write_tables: dict[str, int]
    kafka_topics: list[str]
    updated_at: str


class RequestTimelineEvent(BaseModel):
    request_id: str
    event_ts: str
    event_type: str
    stage_name: str | None = None
    status: str | None = None
    message: str | None = None
    latency_ms: int | None = None
    payload: str | None = None


class AdminRequestList(BaseModel):
    items: list[InferenceRequest]
    source: str
    limit: int
    table: str
    page: int
    page_size: int
    returned: int
    has_next: bool
    updated_at: str


class UserRequestList(BaseModel):
    items: list[InferenceRequest]
    source: str
    limit: int
    page: int
    page_size: int
    returned: int
    has_next: bool
    days: int
    updated_at: str


class ProteinRequestList(BaseModel):
    protein_id: str
    items: list[InferenceRequest]
    source: str
    limit: int
    returned: int
    updated_at: str


class RequestHistoryClearResponse(BaseModel):
    status: str
    truncated_tables: list[str]
    cleared_memory_items: int
    updated_at: str


class RequestDeleteResponse(BaseModel):
    status: str
    request_id: str
    deleted_tables: list[str]
    cleared_memory_items: int
    updated_at: str


security = HTTPBearer()
app = FastAPI(title="BioInformatics Serving API")
REVOKED_TOKEN_IDS: set[str] = set()


class AppState:
    cassandra: CassandraStore | None = None
    cassandra_error: str | None = None


state_store = AppState()

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5174,http://127.0.0.1:5174",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def app_now() -> datetime:
    return datetime.now(APP_TIMEZONE)


def serialize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: serialize_value(value) for key, value in row.items()}


def get_cassandra_store() -> CassandraStore:
    if state_store.cassandra is None:
        detail = "Cassandra is not initialized"
        if state_store.cassandra_error:
            detail = f"{detail}: {state_store.cassandra_error}"
        raise HTTPException(status_code=503, detail=detail)
    return state_store.cassandra


@app.on_event("startup")
def startup() -> None:
    try:
        state_store.cassandra = CassandraStore(CassandraConfig())
        state_store.cassandra_error = None
    except Exception as exc:
        state_store.cassandra = None
        state_store.cassandra_error = str(exc)


@app.on_event("shutdown")
def shutdown() -> None:
    if state_store.cassandra:
        state_store.cassandra.close()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


ADMIN_USERNAME = (os.getenv("ADMIN_USERNAME", "admin").strip() or "admin").lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
USER_STORE_PATH = os.getenv("USER_STORE_PATH", "tmp/auth_users.json")
USER_STORE_LOCK = threading.Lock()

USERS = {
    ADMIN_USERNAME: {
        "password_hash": hash_password(ADMIN_PASSWORD),
        "display_name": ADMIN_USERNAME,
        "roles": ["user", "admin"],
    },
}


def normalize_roles(roles: Any) -> list[Role]:
    if not isinstance(roles, list):
        return ["user"]
    normalized = {"user" if role == "operator" else str(role) for role in roles}
    normalized.discard("")
    if "admin" in normalized:
        normalized.add("user")
    if not normalized:
        normalized.add("user")
    return sorted(normalized)


def load_registered_users() -> None:
    if not os.path.exists(USER_STORE_PATH):
        return
    try:
        with open(USER_STORE_PATH, encoding="utf-8") as user_file:
            stored_users = json.load(user_file)
    except (OSError, json.JSONDecodeError):
        return

    if not isinstance(stored_users, dict):
        return
    for username, user in stored_users.items():
        normalized_username = str(username).strip().lower()
        if not normalized_username or normalized_username == ADMIN_USERNAME:
            continue
        if not isinstance(user, dict):
            continue
        password_hash = user.get("password_hash")
        if not isinstance(password_hash, str) or not password_hash:
            continue
        USERS[normalized_username] = {
            "password_hash": password_hash,
            "display_name": normalized_username,
            "roles": normalize_roles(user.get("roles", ["user"])),
        }


def save_registered_users() -> None:
    stored_users = {
        username: {
            "password_hash": user["password_hash"],
            "roles": ["user"],
        }
        for username, user in USERS.items()
        if username != ADMIN_USERNAME and "user" in user["roles"]
    }
    directory = os.path.dirname(USER_STORE_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(USER_STORE_PATH, "w", encoding="utf-8") as user_file:
        json.dump(stored_users, user_file, indent=2, sort_keys=True)


load_registered_users()

REQUESTS: list[InferenceRequest] = []
PREDICTIONS: list[LatestPrediction] = []
REQUEST_INPUTS: dict[str, RequestInput] = {}
REQUEST_LATENCIES_MS: dict[str, int] = {}
KAFKA_PRODUCER: Any | None = None
CASSANDRA_READER: Any | None = None


class SseBroadcaster:
    def __init__(self) -> None:
        self._clients: set[queue.Queue[str]] = set()
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue[str]:
        client: queue.Queue[str] = queue.Queue(maxsize=50)
        with self._lock:
            self._clients.add(client)
        return client

    def unsubscribe(self, client: queue.Queue[str]) -> None:
        with self._lock:
            self._clients.discard(client)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        message = (
            f"event: {event_type}\n"
            f"data: {json.dumps(payload, default=serialize_value)}\n\n"
        )
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            try:
                client.put_nowait(message)
            except queue.Full:
                pass


USER_BROADCASTER = SseBroadcaster()


def serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(APP_TIMEZONE).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): serialize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [serialize_value(item) for item in value]
    return value


def row_to_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "_asdict"):
        return {key: serialize_value(value) for key, value in row._asdict().items()}
    if isinstance(row, dict):
        return {key: serialize_value(value) for key, value in row.items()}
    return {}


class CassandraReader:
    def __init__(self) -> None:
        try:
            from cassandra.cluster import Cluster
        except ImportError as exc:
            raise RuntimeError("Install cassandra-driver to query Cassandra") from exc

        hosts = os.getenv("CASSANDRA_HOSTS", os.getenv("CASSANDRA_HOST", "localhost"))
        host_list = [host.strip() for host in hosts.split(",") if host.strip()]
        self._cluster = Cluster(host_list, port=int(os.getenv("CASSANDRA_PORT", "9042")))
        self._session = self._cluster.connect(os.getenv("CASSANDRA_KEYSPACE", "protein_rt"))

    def list_requests(
        self,
        request_date: date,
        limit: int,
        table: str = "requests_by_day",
        status_filter: str | None = None,
        username: str | None = None,
    ) -> list[dict[str, Any]]:
        if table == "requests_by_status_window" or status_filter:
            bucket = f"{request_date.isoformat()}#{status_filter.lower()}"
            rows = self._session.execute(
                "SELECT * FROM requests_by_status_window WHERE status_bucket = %s LIMIT %s",
                (bucket, limit),
            )
        elif table == "requests_by_user_window" or username:
            bucket = f"{request_date.isoformat()}#{username}"
            rows = self._session.execute(
                "SELECT * FROM requests_by_user_window WHERE username_bucket = %s LIMIT %s",
                (bucket, limit),
            )
        else:
            rows = self._session.execute(
                "SELECT * FROM requests_by_day WHERE request_date = %s LIMIT %s",
                (request_date, limit),
            )

        items = [row_to_dict(row) for row in rows]
        if username and status_filter:
            items = [item for item in items if item.get("username") == username]
        return items[:limit]

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        rows = self._session.execute(
            "SELECT * FROM request_status_by_id WHERE request_id = %s LIMIT 1",
            (request_id,),
        )
        for row in rows:
            return row_to_dict(row)
        return None

    def list_requests_by_protein(self, protein_id: str, limit: int) -> list[dict[str, Any]]:
        rows = self._session.execute(
            """
            SELECT * FROM requests_by_protein_window
            WHERE protein_bucket = %s LIMIT %s
            """,
            (protein_id.lower(), limit),
        )
        return [row_to_dict(row) for row in rows]

    def clear_request_history(self) -> list[str]:
        tables = [
            "request_status_by_id",
            "requests_by_day",
            "requests_by_status_window",
            "requests_by_user_window",
            "requests_by_protein_window",
            "request_timeline_by_id",
            "latest_prediction_by_protein",
            "prediction_history_by_protein",
            "pipeline_metrics_by_window",
            "cassandra_serving_stats_by_day",
        ]
        for table in tables:
            self._session.execute(f"TRUNCATE {table}")
        return tables

    def delete_request(
        self,
        request_id: str,
        fallback_request_row: dict[str, Any] | None = None,
    ) -> list[str]:
        request_row = self.get_request(request_id) or fallback_request_row
        if not request_row:
            return []

        deleted_tables: list[str] = []

        self._session.execute(
            "DELETE FROM request_status_by_id WHERE request_id = %s",
            (request_id,),
        )
        deleted_tables.append("request_status_by_id")

        request_date = request_row.get("request_date")
        created_at = request_row.get("created_at")
        updated_at = request_row.get("updated_at") or created_at
        current_status = request_row.get("current_status")
        username = request_row.get("username")
        protein_id = request_row.get("protein_id")

        if request_date is not None and not isinstance(request_date, date):
            request_date = date.fromisoformat(str(request_date))
        if isinstance(created_at, str):
            created_at = parse_iso_datetime(created_at)
        if isinstance(updated_at, str):
            updated_at = parse_iso_datetime(updated_at)

        if request_date is None and created_at is not None:
            request_date = (
                created_at.date()
                if isinstance(created_at, datetime)
                else parse_iso_datetime(str(created_at)).date()
            )

        if request_date is not None and created_at is not None:
            self._session.execute(
                """
                DELETE FROM requests_by_day
                WHERE request_date = %s AND created_at = %s AND request_id = %s
                """,
                (request_date, created_at, request_id),
            )
            deleted_tables.append("requests_by_day")

        if request_date is not None and updated_at is not None and current_status:
            status_bucket = f"{request_date.isoformat()}#{str(current_status).lower()}"
            self._session.execute(
                """
                DELETE FROM requests_by_status_window
                WHERE status_bucket = %s AND updated_at = %s AND request_id = %s
                """,
                (status_bucket, updated_at, request_id),
            )
            deleted_tables.append("requests_by_status_window")

        if request_date is not None and username and created_at is not None:
            username_bucket = f"{request_date.isoformat()}#{username}"
            self._session.execute(
                """
                DELETE FROM requests_by_user_window
                WHERE username_bucket = %s AND created_at = %s AND request_id = %s
                """,
                (username_bucket, created_at, request_id),
            )
            deleted_tables.append("requests_by_user_window")

        if protein_id and created_at is not None:
            self._session.execute(
                """
                DELETE FROM requests_by_protein_window
                WHERE protein_bucket = %s AND created_at = %s AND request_id = %s
                """,
                (str(protein_id).lower(), created_at, request_id),
            )
            deleted_tables.append("requests_by_protein_window")

        self._session.execute(
            "DELETE FROM request_timeline_by_id WHERE request_id = %s",
            (request_id,),
        )
        deleted_tables.append("request_timeline_by_id")

        if protein_id:
            for row in self.prediction_history_by_protein(str(protein_id), limit=200):
                if str(row.get("request_id")) != request_id:
                    continue
                predicted_at = row.get("predicted_at")
                if predicted_at is None:
                    continue
                if isinstance(predicted_at, str):
                    predicted_at = parse_iso_datetime(predicted_at)
                self._session.execute(
                    """
                    DELETE FROM prediction_history_by_protein
                    WHERE protein_id = %s AND predicted_at = %s AND request_id = %s
                    """,
                    (str(protein_id), predicted_at, request_id),
                )
                if "prediction_history_by_protein" not in deleted_tables:
                    deleted_tables.append("prediction_history_by_protein")

            latest_rows = self._session.execute(
                "SELECT request_id FROM latest_prediction_by_protein WHERE protein_id = %s LIMIT 1",
                (str(protein_id),),
            )
            for latest_row in latest_rows:
                if str(getattr(latest_row, "request_id", "")) == request_id:
                    self._session.execute(
                        "DELETE FROM latest_prediction_by_protein WHERE protein_id = %s",
                        (str(protein_id),),
                    )
                    deleted_tables.append("latest_prediction_by_protein")
                break

        return deleted_tables

    def request_timeline(self, request_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._session.execute(
            "SELECT * FROM request_timeline_by_id WHERE request_id = %s LIMIT %s",
            (request_id, limit),
        )
        return [row_to_dict(row) for row in rows]

    def prediction_history_by_protein(self, protein_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._session.execute(
            """
            SELECT * FROM prediction_history_by_protein
            WHERE protein_id = %s LIMIT %s
            """,
            (protein_id, limit),
        )
        return [row_to_dict(row) for row in rows]

    def pipeline_metric(self, metric_name: str, metric_date: date, limit: int = 8) -> list[dict[str, Any]]:
        rows = self._session.execute(
            """
            SELECT * FROM pipeline_metrics_by_window
            WHERE metric_date = %s AND metric_name = %s LIMIT %s
            """,
            (metric_date, metric_name, limit),
        )
        return [row_to_dict(row) for row in rows]


def get_cassandra_reader() -> CassandraReader | None:
    global CASSANDRA_READER
    if CASSANDRA_READER is not None:
        return CASSANDRA_READER
    try:
        CASSANDRA_READER = CassandraReader()
    except Exception:
        CASSANDRA_READER = None
    return CASSANDRA_READER


def get_kafka_producer() -> Any | None:
    global KAFKA_PRODUCER
    if KAFKA_PRODUCER is not None:
        return KAFKA_PRODUCER
    try:
        from kafka import KafkaProducer

        KAFKA_PRODUCER = KafkaProducer(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093"),
            value_serializer=lambda payload: json.dumps(payload).encode("utf-8"),
            key_serializer=lambda key: key.encode("utf-8"),
            linger_ms=10,
        )
    except Exception:
        KAFKA_PRODUCER = None
    return KAFKA_PRODUCER


def publish_pipeline_event(topic: str, key: str, payload: dict[str, Any]) -> None:
    producer = get_kafka_producer()
    if producer is None:
        return
    try:
        producer.send(topic, key=key, value=payload)
        producer.flush(timeout=2)
    except Exception:
        pass


def request_to_event(
    request: InferenceRequest,
    username: str,
    source: str,
    latency_ms: int | None = None,
    sequence: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        **request.model_dump(),
        "username": username,
        "source": source,
        "event_ts": request.updated_at or request.created_at,
        "latency_ms": latency_ms,
    }
    if sequence is not None:
        event["sequence"] = sequence
        event["sequence_length"] = len(sequence)
    if metadata is not None:
        event["metadata"] = metadata
    return event


def base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def base64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(f"{raw}{padding}".encode("ascii"))


def sign_jwt_part(signing_input: str) -> str:
    signature = hmac.new(
        JWT_SECRET.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return base64url_encode(signature)


def create_access_token(user: UserPublic) -> str:
    now = int(time.time())
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload = {
        "sub": user.username,
        "roles": user.roles,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + JWT_EXPIRES_SECONDS,
    }
    encoded_header = base64url_encode(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    encoded_payload = base64url_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}"
    return f"{signing_input}.{sign_jwt_part(signing_input)}"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        encoded_header, encoded_payload, signature = token.split(".")
        signing_input = f"{encoded_header}.{encoded_payload}"
        expected_signature = sign_jwt_part(signing_input)
        header = json.loads(base64url_decode(encoded_header))
        payload = json.loads(base64url_decode(encoded_payload))
    except (ValueError, json.JSONDecodeError):
        raise unauthorized("Invalid access token") from None

    if header.get("alg") != JWT_ALGORITHM:
        raise unauthorized("Unsupported token algorithm")

    if not hmac.compare_digest(signature, expected_signature):
        raise unauthorized("Invalid access token signature")

    if int(payload.get("exp", 0)) < int(time.time()):
        raise unauthorized("Access token expired")

    token_id = payload.get("jti")
    if isinstance(token_id, str) and token_id in REVOKED_TOKEN_IDS:
        raise unauthorized("Access token has been revoked")

    return payload


def unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def user_public(username: str) -> UserPublic:
    user = USERS.get(username)
    if not user:
        raise unauthorized("Unknown user")
    return UserPublic(
        username=username,
        display_name=username,
        roles=list(user["roles"]),
    )


def build_admin_user_list() -> AdminUserList:
    items = [
        AdminUserItem(
            username=username,
            roles=list(user["roles"]),
            is_admin="admin" in user["roles"],
        )
        for username, user in sorted(USERS.items())
    ]
    return AdminUserList(
        items=items,
        returned=len(items),
        updated_at=app_now().isoformat(),
    )


def publish_admin_users() -> None:
    USER_BROADCASTER.publish(
        "admin_users",
        build_admin_user_list().model_dump(),
    )


def get_current_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    return decode_access_token(credentials.credentials)


def get_current_user(
    payload: dict[str, Any] = Depends(get_current_token_payload),
) -> UserPublic:
    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise unauthorized("Invalid access token subject")
    return user_public(subject)


def require_roles(*allowed_roles: Role):
    def dependency(current_user: UserPublic = Depends(get_current_user)) -> UserPublic:
        if not set(current_user.roles).intersection(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have permission for this action",
            )
        return current_user

    return dependency


def parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=APP_TIMEZONE)
    return parsed.astimezone(APP_TIMEZONE)


def build_throughput(requests: list[InferenceRequest]) -> list[PipelineMetricPoint]:
    now_minute = app_now().replace(second=0, microsecond=0)
    points: list[PipelineMetricPoint] = []
    for index in range(8):
        start = now_minute - timedelta(minutes=7 - index)
        end = start + timedelta(minutes=1)
        value = 0
        for request in requests:
            try:
                request_ts = parse_iso_datetime(request.created_at)
            except ValueError:
                continue
            if start <= request_ts < end:
                value += 1
        points.append(
            PipelineMetricPoint(
                window_start=start.isoformat(),
                window_end=end.isoformat(),
                metric_name="events_per_minute",
                metric_value=value,
                tags={"source": "serving_api_requests"},
            )
        )
    return points


def calculate_latency_ms() -> tuple[int, int]:
    values = sorted(REQUEST_LATENCIES_MS.values())
    if not values:
        return 0, 0

    average = round(sum(values) / len(values))
    p95_index = min(len(values) - 1, round((len(values) - 1) * 0.95))
    return average, values[p95_index]


def is_today(iso_timestamp: str) -> bool:
    return parse_iso_datetime(iso_timestamp).date() == app_now().date()


def latest_predictions(limit: int = 10) -> list[LatestPrediction]:
    return sorted(PREDICTIONS, key=lambda item: item.predicted_at, reverse=True)[:limit]


def prediction_for_request(request_id: str) -> LatestPrediction | None:
    return next(
        (
            prediction
            for prediction in PREDICTIONS
            if prediction.request_id == request_id
        ),
        None,
    )


def delete_request_from_memory(request_id: str) -> int:
    cleared_items = 0

    original_request_count = len(REQUESTS)
    REQUESTS[:] = [request for request in REQUESTS if request.request_id != request_id]
    cleared_items += original_request_count - len(REQUESTS)

    original_prediction_count = len(PREDICTIONS)
    PREDICTIONS[:] = [
        prediction for prediction in PREDICTIONS if prediction.request_id != request_id
    ]
    cleared_items += original_prediction_count - len(PREDICTIONS)

    if request_id in REQUEST_INPUTS:
        del REQUEST_INPUTS[request_id]
        cleared_items += 1

    if request_id in REQUEST_LATENCIES_MS:
        del REQUEST_LATENCIES_MS[request_id]
        cleared_items += 1

    return cleared_items


def input_from_event_payload(payload: dict[str, Any]) -> RequestInput | None:
    protein_id = payload.get("protein_id")
    if not protein_id:
        return None

    sequence = payload.get("sequence")
    sequence_text = str(sequence) if sequence is not None else None
    metadata = payload.get("metadata")

    return RequestInput(
        protein_id=str(protein_id),
        sequence=sequence_text,
        sequence_length=(
            len(sequence_text)
            if sequence_text is not None
            else int(payload["sequence_length"])
            if payload.get("sequence_length") is not None
            else None
        ),
        source=str(payload["source"]) if payload.get("source") is not None else None,
        metadata=metadata if isinstance(metadata, dict) else None,
    )


def cassandra_input_for_request(request: InferenceRequest) -> RequestInput | None:
    reader = get_cassandra_reader()
    if not reader:
        return None

    try:
        for event in reader.request_timeline(request.request_id):
            payload = event.get("payload")
            if not payload:
                continue
            parsed_payload = json.loads(str(payload))
            if isinstance(parsed_payload, dict):
                request_input = input_from_event_payload(parsed_payload)
                if request_input and (
                    request_input.sequence or request_input.sequence_length
                ):
                    return request_input
    except Exception:
        pass

    return None


def input_from_server_result(
    request: InferenceRequest,
    server_result: dict[str, Any] | None,
) -> RequestInput | None:
    if not server_result:
        return None

    records = server_result.get("records")
    if not isinstance(records, list):
        return None

    for record in records:
        if not isinstance(record, dict):
            continue
        protein_id = str(record.get("protein_id", request.protein_id))
        if protein_id.lower() != request.protein_id.lower():
            continue

        sequence_preview = record.get("sequence_preview")
        sequence_text = str(sequence_preview) if sequence_preview is not None else None
        sequence_length = record.get("length")
        return RequestInput(
            protein_id=protein_id,
            sequence=sequence_text,
            sequence_length=(
                int(sequence_length)
                if sequence_length is not None
                else len(sequence_text)
                if sequence_text is not None
                else None
            ),
            source=request.source,
            metadata={"sequence_preview_only": True} if sequence_text else None,
        )

    return None


def parse_obo_quoted_value(value: str) -> str | None:
    start = value.find('"')
    if start < 0:
        return None

    result: list[str] = []
    escaped = False
    for char in value[start + 1 :]:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            return "".join(result)
        result.append(char)
    return None


@lru_cache(maxsize=1)
def load_go_term_definitions() -> dict[str, dict[str, str]]:
    path = os.getenv("GO_BASIC_OBO_PATH", "docs/go-basic.obo")
    terms: dict[str, dict[str, str]] = {}

    try:
        with open(path, encoding="utf-8") as obo_file:
            blocks = obo_file.read().split("\n[Term]\n")
    except OSError:
        return terms

    for block in blocks[1:]:
        term_id: str | None = None
        name: str | None = None
        namespace: str | None = None
        definition: str | None = None
        is_obsolete = False

        for line in block.splitlines():
            if line.startswith("["):
                break
            if line.startswith("id: "):
                term_id = line[4:].strip()
            elif line.startswith("name: "):
                name = line[6:].strip()
            elif line.startswith("namespace: "):
                namespace = line[11:].strip()
            elif line.startswith("def: "):
                definition = parse_obo_quoted_value(line[5:].strip())
            elif line == "is_obsolete: true":
                is_obsolete = True

        if term_id and not is_obsolete:
            terms[term_id] = {
                "name": name or "",
                "namespace": namespace or "",
                "definition": definition or "",
            }

    return terms


def go_term_metadata(term_id: str) -> dict[str, str]:
    return load_go_term_definitions().get(term_id, {})


def enrich_prediction_term(term: PredictionTerm) -> PredictionTerm:
    metadata = go_term_metadata(term.term_id)
    if not metadata:
        return term

    return PredictionTerm(
        term_id=term.term_id,
        term_name=term.term_name or metadata.get("name") or None,
        ontology=term.ontology or map_namespace_value(metadata.get("namespace")),
        score=term.score,
        definition=term.definition or metadata.get("definition") or None,
    )


def enrich_prediction_terms(terms: list[PredictionTerm]) -> list[PredictionTerm]:
    return [enrich_prediction_term(term) for term in terms]


def prediction_from_event_payload(payload: dict[str, Any]) -> LatestPrediction | None:
    protein_id = payload.get("protein_id")
    request_id = payload.get("request_id")
    if not protein_id or not request_id:
        return None

    top_terms_payload = payload.get("top_terms", [])
    top_terms: list[PredictionTerm] = []
    if isinstance(top_terms_payload, list):
        for item in top_terms_payload:
            if isinstance(item, dict):
                term_id = item.get("term_id") or item.get("go_term")
                if not term_id:
                    continue
                top_terms.append(
                    enrich_prediction_term(
                        PredictionTerm(
                            term_id=str(term_id),
                            term_name=(
                                str(item["term_name"])
                                if item.get("term_name") is not None
                                else str(item["name"])
                                if item.get("name") is not None
                                else None
                            ),
                            ontology=map_aspect_value(item.get("ontology") or item.get("aspect")),
                            score=float(item.get("score", 0)),
                        )
                    )
                )
            elif item:
                top_terms.append(enrich_prediction_term(PredictionTerm(term_id=str(item), score=0)))

    server_result = payload.get("server_result")
    return LatestPrediction(
        protein_id=str(protein_id),
        request_id=str(request_id),
        predicted_at=str(payload.get("predicted_at") or payload.get("event_ts") or app_now().isoformat()),
        model_version=str(payload.get("model_version") or "unknown"),
        top_terms=enrich_prediction_terms(top_terms),
        confidence_summary=(
            str(payload["confidence_summary"])
            if payload.get("confidence_summary") is not None
            else None
        ),
        server_result=server_result if isinstance(server_result, dict) else None,
    )


def prediction_from_history_row(row: dict[str, Any]) -> LatestPrediction:
    top_terms_payload = row.get("top_terms") or []
    top_scores_payload = row.get("top_scores") or []
    top_terms: list[PredictionTerm] = []
    if isinstance(top_terms_payload, list):
        for index, term_id in enumerate(top_terms_payload):
            score = 0.0
            if isinstance(top_scores_payload, list) and index < len(top_scores_payload):
                score = float(top_scores_payload[index])
            top_terms.append(enrich_prediction_term(PredictionTerm(term_id=str(term_id), score=score)))

    return LatestPrediction(
        protein_id=str(row.get("protein_id", "")),
        request_id=str(row.get("request_id", "")),
        predicted_at=str(row.get("predicted_at") or app_now().isoformat()),
        model_version=str(row.get("model_version") or "unknown"),
        top_terms=enrich_prediction_terms(top_terms),
        confidence_summary=(
            str(row["confidence_summary"])
            if row.get("confidence_summary") is not None
            else None
        ),
        server_result=None,
    )


def map_aspect_value(aspect: Any) -> str | None:
    return {
        "F": "MF",
        "P": "BP",
        "C": "CC",
        "MF": "MF",
        "BP": "BP",
        "CC": "CC",
    }.get(str(aspect), None)


def map_namespace_value(namespace: Any) -> str | None:
    return {
        "molecular_function": "MF",
        "biological_process": "BP",
        "cellular_component": "CC",
    }.get(str(namespace), None)


def cassandra_prediction_for_request(request: InferenceRequest) -> LatestPrediction | None:
    reader = get_cassandra_reader()
    if not reader:
        return None

    try:
        for event in reader.request_timeline(request.request_id):
            if event.get("event_type") != "prediction_result":
                continue
            payload = event.get("payload")
            if not payload:
                continue
            parsed_payload = json.loads(str(payload))
            if isinstance(parsed_payload, dict):
                prediction = prediction_from_event_payload(parsed_payload)
                if prediction:
                    return prediction
    except Exception:
        pass

    try:
        for row in reader.prediction_history_by_protein(request.protein_id):
            if str(row.get("request_id")) == request.request_id:
                return prediction_from_history_row(row)
    except Exception:
        pass

    return None


def inference_request_from_row(row: dict[str, Any]) -> InferenceRequest:
    return InferenceRequest(
        request_id=str(row.get("request_id", "")),
        protein_id=str(row.get("protein_id", "")),
        username=str(row.get("username")) if row.get("username") is not None else None,
        source=str(row.get("source")) if row.get("source") is not None else None,
        created_at=str(row.get("created_at") or row.get("updated_at") or app_now().isoformat()),
        updated_at=str(row.get("updated_at")) if row.get("updated_at") is not None else None,
        current_status=str(row.get("current_status", "processing")).lower(),
        stage_name=row.get("stage_name"),
        error_code=row.get("error_code"),
        error_message=row.get("error_message"),
        retry_count=int(row.get("retry_count", 0) or 0),
        model_version=row.get("model_version"),
        feature_version=row.get("feature_version"),
    )


def recent_requests_from_cassandra(limit: int = 20) -> list[InferenceRequest]:
    reader = get_cassandra_reader()
    if not reader:
        return []
    try:
        rows = reader.list_requests(app_now().date(), limit)
    except Exception:
        return []
    return [inference_request_from_row(row) for row in rows]


def user_is_admin(user: UserPublic) -> bool:
    return "admin" in user.roles


def can_access_request(request: InferenceRequest, user: UserPublic) -> bool:
    return user_is_admin(user) or request.username == user.username


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/requests/{request_id}")
def get_cassandra_request_status(request_id: str) -> dict[str, Any]:
    store = get_cassandra_store()
    row = serialize_row(store.get_request_status(request_id))
    if row is None:
        raise HTTPException(status_code=404, detail="request_id not found")
    return row


@app.get("/v1/requests/{request_id}/prediction")
def get_cassandra_request_prediction(request_id: str) -> dict[str, Any]:
    store = get_cassandra_store()
    row = serialize_row(store.get_prediction_by_request(request_id))
    if row is None:
        raise HTTPException(status_code=404, detail="prediction for request_id not found")
    return row


@app.get("/v1/proteins/{protein_id}/latest")
def get_cassandra_latest_prediction(protein_id: str) -> dict[str, Any]:
    store = get_cassandra_store()
    row = serialize_row(store.get_latest_prediction(protein_id))
    if row is None:
        raise HTTPException(status_code=404, detail="protein_id not found")
    return row


@app.get("/v1/proteins/{protein_id}/history")
def get_cassandra_prediction_history(
    protein_id: str,
    limit: int = Query(default=20, ge=1, le=200),
) -> list[dict[str, Any]]:
    store = get_cassandra_store()
    return [serialize_row(row) or {} for row in store.get_prediction_history(protein_id, limit)]


@app.post("/api/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    username = payload.username.strip().lower()
    user = USERS.get(username)
    if not user or not hmac.compare_digest(
        str(user["password_hash"]),
        hash_password(payload.password),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    public_user = user_public(username)
    return LoginResponse(
        access_token=create_access_token(public_user),
        expires_in=JWT_EXPIRES_SECONDS,
        user=public_user,
    )


@app.post(
    "/api/auth/register",
    response_model=LoginResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: RegisterRequest) -> LoginResponse:
    username = payload.username.strip().lower()
    password = payload.password

    if not username:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="username is required",
        )
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="password must be at least 8 characters",
        )

    with USER_STORE_LOCK:
        if username in USERS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )
        USERS[username] = {
            "password_hash": hash_password(password),
            "display_name": username,
            "roles": ["user"],
        }
        save_registered_users()
        publish_admin_users()

    public_user = user_public(username)
    return LoginResponse(
        access_token=create_access_token(public_user),
        expires_in=JWT_EXPIRES_SECONDS,
        user=public_user,
    )


@app.post("/api/auth/logout")
def logout(payload: dict[str, Any] = Depends(get_current_token_payload)) -> dict[str, str]:
    token_id = payload.get("jti")
    if isinstance(token_id, str):
        REVOKED_TOKEN_IDS.add(token_id)
    return {"status": "ok"}


@app.get("/api/auth/me", response_model=UserPublic)
def me(current_user: UserPublic = Depends(get_current_user)) -> UserPublic:
    return current_user


@app.get("/api/admin/users", response_model=AdminUserList)
def list_admin_users(
    _: UserPublic = Depends(require_roles("admin")),
) -> AdminUserList:
    return build_admin_user_list()


@app.get("/api/admin/users/events")
def admin_user_events(token: str = Query(default="")) -> StreamingResponse:
    payload = decode_access_token(token)
    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise unauthorized("Invalid access token subject")
    current_user = user_public(subject)
    if "admin" not in current_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have permission for this action",
        )

    client = USER_BROADCASTER.subscribe()

    def stream() -> Iterator[str]:
        try:
            yield (
                "event: admin_users\n"
                f"data: {build_admin_user_list().model_dump_json()}\n\n"
            )
            while True:
                try:
                    yield client.get(timeout=20)
                except queue.Empty:
                    yield "event: heartbeat\ndata: {}\n\n"
        finally:
            USER_BROADCASTER.unsubscribe(client)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/api/admin/users/{username}", response_model=AdminUserList)
def delete_admin_user(
    username: str,
    _: UserPublic = Depends(require_roles("admin")),
) -> AdminUserList:
    normalized_username = username.strip().lower()
    if normalized_username == ADMIN_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot delete the configured admin account",
        )
    if normalized_username not in USERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    with USER_STORE_LOCK:
        USERS.pop(normalized_username, None)
        save_registered_users()
        publish_admin_users()

    return build_admin_user_list()


@app.get("/api/metrics/pipeline/summary", response_model=DashboardSummary)
def get_pipeline_summary(
    window: str = Query(default="minute"),
    current_user: UserPublic = Depends(require_roles("user", "admin")),
) -> DashboardSummary:
    reader = get_cassandra_reader()
    cassandra_requests: list[InferenceRequest] = []
    if reader:
        try:
            if user_is_admin(current_user):
                rows = reader.list_requests(app_now().date(), 50)
            else:
                rows = reader.list_requests(
                    app_now().date(),
                    50,
                    table="requests_by_user_window",
                    username=current_user.username,
                )
            cassandra_requests = [inference_request_from_row(row) for row in rows]
        except Exception:
            cassandra_requests = []
    summary_requests = cassandra_requests or REQUESTS
    if not user_is_admin(current_user):
        summary_requests = [
            request for request in summary_requests if request.username == current_user.username
        ]
    status_counts = {
        "pending": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0,
        "retrying": 0,
        "cancelled": 0,
    }
    for request in summary_requests:
        status_counts[request.current_status] = (
            status_counts.get(request.current_status, 0) + 1
        )

    total_today = sum(1 for request in summary_requests if is_today(request.created_at))
    failed_count = status_counts.get("failed", 0)
    error_rate = failed_count / len(summary_requests) if summary_requests else 0
    avg_latency_ms, p95_latency_ms = calculate_latency_ms()
    error_counts = Counter(
        request.error_code or "UNKNOWN"
        for request in summary_requests
        if request.current_status == "failed"
    )
    visible_request_ids = {request.request_id for request in summary_requests}
    visible_predictions = [
        prediction
        for prediction in latest_predictions()
        if prediction.request_id in visible_request_ids or user_is_admin(current_user)
    ]
    return DashboardSummary(
        total_today=total_today,
        status_counts=status_counts,
        avg_latency_ms=avg_latency_ms,
        p95_latency_ms=p95_latency_ms,
        error_rate=round(error_rate, 4),
        throughput=build_throughput(summary_requests),
        recent_requests=summary_requests[:12],
        recent_predictions=visible_predictions,
        recent_failed_requests=[
            request for request in summary_requests if request.current_status == "failed"
        ],
        error_counts=dict(error_counts.most_common(8)),
        cassandra_query_patterns=[
            "request_status_by_id",
            "requests_by_day",
            "requests_by_status_window",
            "requests_by_user_window",
            "requests_by_protein_window",
            "request_timeline_by_id",
            "prediction_history_by_protein",
            "pipeline_metrics_by_window",
        ],
        cassandra_write_tables={
            "request_status_by_id": total_today,
            "requests_by_day": total_today,
            "requests_by_status_window": total_today,
            "requests_by_user_window": total_today,
            "requests_by_protein_window": total_today,
            "request_timeline_by_id": total_today,
        },
        kafka_topics=[
            os.getenv("KAFKA_REQUEST_STATUS_TOPIC", "request_status"),
            os.getenv("KAFKA_PREDICTION_TOPIC", "prediction_result"),
            os.getenv("KAFKA_DEAD_LETTER_TOPIC", "dead_letter"),
        ],
        updated_at=app_now().isoformat(),
    )


@app.post(
    "/api/inference-requests",
    response_model=InferenceRequest,
    status_code=status.HTTP_201_CREATED,
)
def create_inference_request(
    payload: CreateInferenceRequestPayload,
    current_user: UserPublic = Depends(require_roles("user", "admin")),
) -> InferenceRequest:
    request_id = f"api-{uuid.uuid4()}"
    created_at = app_now().isoformat()
    protein_id = payload.protein_id.strip()

    if not protein_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="protein_id is required",
        )

    accepted = InferenceRequest(
        request_id=request_id,
        protein_id=protein_id,
        username=current_user.username,
        source=payload.source,
        created_at=created_at,
        updated_at=created_at,
        current_status="processing",
        stage_name="accepted",
        retry_count=0,
    )
    normalized_sequence = "".join(payload.sequence.upper().split())
    REQUEST_INPUTS[request_id] = RequestInput(
        protein_id=protein_id,
        sequence=normalized_sequence,
        sequence_length=len(normalized_sequence),
        source=payload.source,
        metadata=payload.metadata,
    )
    publish_pipeline_event(
        os.getenv("KAFKA_REQUEST_STATUS_TOPIC", "request_status"),
        request_id,
        request_to_event(
            accepted,
            username=current_user.username,
            source=payload.source,
            sequence=normalized_sequence,
            metadata=payload.metadata,
        ),
    )

    try:
        analysis = run_cafa6_analysis(protein_id=protein_id, sequence=normalized_sequence)
    except Cafa6ValidationError as exc:
        failed = InferenceRequest(
            request_id=request_id,
            protein_id=protein_id,
            username=current_user.username,
            source=payload.source,
            created_at=created_at,
            updated_at=app_now().isoformat(),
            current_status="failed",
            stage_name="validation",
            error_code="INVALID_SEQUENCE",
            error_message=str(exc),
            retry_count=0,
        )
        REQUESTS.insert(0, failed)
        publish_pipeline_event(
            os.getenv("KAFKA_REQUEST_STATUS_TOPIC", "request_status"),
            request_id,
            request_to_event(
                failed,
                username=current_user.username,
                source=payload.source,
                sequence=normalized_sequence,
                metadata=payload.metadata,
            ),
        )
        return failed
    except Cafa6AnalysisError as exc:
        failed = InferenceRequest(
            request_id=request_id,
            protein_id=protein_id,
            username=current_user.username,
            source=payload.source,
            created_at=created_at,
            updated_at=app_now().isoformat(),
            current_status="failed",
            stage_name="external_analysis",
            error_code="ANALYSIS_API_ERROR",
            error_message=str(exc),
            retry_count=0,
        )
        REQUESTS.insert(0, failed)
        publish_pipeline_event(
            os.getenv("KAFKA_REQUEST_STATUS_TOPIC", "request_status"),
            request_id,
            request_to_event(
                failed,
                username=current_user.username,
                source=payload.source,
                sequence=normalized_sequence,
                metadata=payload.metadata,
            ),
        )
        return failed

    created = InferenceRequest(
        request_id=request_id,
        protein_id=protein_id,
        username=current_user.username,
        source=payload.source,
        created_at=created_at,
        updated_at=app_now().isoformat(),
        current_status="completed",
        stage_name="prediction_written",
        retry_count=0,
        model_version=analysis.model_version,
        feature_version=analysis.feature_version,
    )
    REQUESTS.insert(0, created)
    REQUEST_LATENCIES_MS[request_id] = analysis.latency_ms

    prediction = LatestPrediction(
        protein_id=protein_id,
        request_id=request_id,
        predicted_at=created.updated_at or app_now().isoformat(),
        model_version=analysis.model_version,
        top_terms=[
            enrich_prediction_term(
                PredictionTerm(
                    term_id=term.term_id,
                    term_name=term.term_name,
                    ontology=term.ontology,
                    score=term.score,
                )
            )
            for term in analysis.top_terms
        ],
        confidence_summary=analysis.confidence_summary,
        server_result=analysis.server_result,
    )
    PREDICTIONS.insert(0, prediction)
    publish_pipeline_event(
        os.getenv("KAFKA_REQUEST_STATUS_TOPIC", "request_status"),
        request_id,
        request_to_event(
            created,
            username=current_user.username,
            source=payload.source,
            latency_ms=analysis.latency_ms,
            sequence=normalized_sequence,
            metadata=payload.metadata,
        ),
    )
    publish_pipeline_event(
        os.getenv("KAFKA_PREDICTION_TOPIC", "prediction_result"),
        request_id,
        {
            "request_id": request_id,
            "protein_id": protein_id,
            "username": current_user.username,
            "source": payload.source,
            "sequence": normalized_sequence,
            "sequence_length": len(normalized_sequence),
            "metadata": payload.metadata,
            "created_at": created.created_at,
            "updated_at": created.updated_at,
            "predicted_at": prediction.predicted_at,
            "current_status": "completed",
            "stage_name": "prediction_written",
            "model_version": analysis.model_version,
            "feature_version": analysis.feature_version,
            "top_terms": [term.model_dump() for term in prediction.top_terms],
            "confidence_summary": prediction.confidence_summary,
            "server_result": analysis.server_result,
            "latency_ms": analysis.latency_ms,
            "event_ts": prediction.predicted_at,
        },
    )
    return created


@app.get("/api/inference-requests/{request_id}", response_model=InferenceRequest)
def get_inference_request(
    request_id: str,
    current_user: UserPublic = Depends(require_roles("user", "admin")),
) -> InferenceRequest:
    reader = get_cassandra_reader()
    if reader:
        try:
            row = reader.get_request(request_id)
            if row:
                request = inference_request_from_row(row)
                if not can_access_request(request, current_user):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="User does not have permission for this request",
                    )
                return request
        except HTTPException:
            raise
        except Exception:
            pass

    for request in REQUESTS:
        if request.request_id == request_id:
            if not can_access_request(request, current_user):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User does not have permission for this request",
                )
            return request

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Request not found",
    )


@app.get("/api/inference-requests/{request_id}/result", response_model=RequestResult)
def get_inference_request_result(
    request_id: str,
    current_user: UserPublic = Depends(require_roles("user", "admin")),
) -> RequestResult:
    request = get_inference_request(request_id, current_user)
    request_input = REQUEST_INPUTS.get(request_id) or cassandra_input_for_request(request)
    prediction = prediction_for_request(request_id) or cassandra_prediction_for_request(request)
    if prediction and prediction.protein_id.lower() != request.protein_id.lower():
        prediction = None
    if not request_input and prediction:
        request_input = input_from_server_result(request, prediction.server_result)

    return RequestResult(
        request=request,
        input=request_input,
        prediction=prediction,
        server_result=prediction.server_result if prediction else None,
    )


@app.get("/api/my/requests", response_model=UserRequestList)
def list_my_requests(
    days: int = Query(default=30, ge=1, le=365),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=5, le=100),
    current_user: UserPublic = Depends(require_roles("user", "admin")),
) -> UserRequestList:
    fetch_limit = page * page_size + 1
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    reader = get_cassandra_reader()

    if reader:
        try:
            rows: list[dict[str, Any]] = []
            today = app_now().date()
            for offset in range(days):
                rows.extend(
                    reader.list_requests(
                        request_date=today - timedelta(days=offset),
                        limit=fetch_limit,
                        table="requests_by_user_window",
                        username=current_user.username,
                    )
                )
                if len(rows) >= fetch_limit:
                    break
            requests = [inference_request_from_row(row) for row in rows]
            requests.sort(
                key=lambda item: item.updated_at or item.created_at,
                reverse=True,
            )
            items = requests[start_index:end_index]
            return UserRequestList(
                items=items,
                source="cassandra",
                limit=page_size,
                page=page,
                page_size=page_size,
                returned=len(items),
                has_next=len(requests) > end_index,
                days=days,
                updated_at=app_now().isoformat(),
            )
        except Exception:
            pass

    filtered_items = [
        request
        for request in REQUESTS
        if request.username == current_user.username
    ]
    filtered_items.sort(
        key=lambda item: item.updated_at or item.created_at,
        reverse=True,
    )
    items = filtered_items[start_index:end_index]
    return UserRequestList(
        items=items,
        source="memory-fallback",
        limit=page_size,
        page=page,
        page_size=page_size,
        returned=len(items),
        has_next=len(filtered_items) > end_index,
        days=days,
        updated_at=app_now().isoformat(),
    )


@app.get("/api/admin/requests", response_model=AdminRequestList)
def list_admin_requests(
    table: str = Query(default="requests_by_day"),
    status_filter: str | None = Query(default=None, alias="status"),
    username: str | None = Query(default=None),
    request_date: date | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=5, le=100),
    _: UserPublic = Depends(require_roles("admin")),
) -> AdminRequestList:
    allowed_tables = {
        "requests_by_day",
        "requests_by_status_window",
        "requests_by_user_window",
    }
    if table not in allowed_tables:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported admin request table",
        )
    if table == "requests_by_status_window" and not status_filter:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status is required when table=requests_by_status_window",
        )
    if table == "requests_by_user_window" and not username:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="username is required when table=requests_by_user_window",
        )

    fetch_limit = page * page_size + 1
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    reader = get_cassandra_reader()
    if reader:
        try:
            rows: list[dict[str, Any]] = []
            query_dates = (
                [request_date]
                if request_date
                else [app_now().date() - timedelta(days=offset) for offset in range(days)]
            )
            for query_date in query_dates:
                rows.extend(
                    reader.list_requests(
                        request_date=query_date,
                        limit=fetch_limit,
                        table=table,
                        status_filter=status_filter,
                        username=username,
                    )
                )
                if len(rows) >= fetch_limit:
                    break
            requests = [inference_request_from_row(row) for row in rows]
            requests.sort(
                key=lambda item: item.updated_at or item.created_at,
                reverse=True,
            )
            paged_requests = requests[start_index:end_index]
            return AdminRequestList(
                items=paged_requests,
                source="cassandra",
                limit=page_size,
                table=table,
                page=page,
                page_size=page_size,
                returned=len(paged_requests),
                has_next=len(requests) > end_index,
                updated_at=app_now().isoformat(),
            )
        except Exception:
            pass

    filtered_items = [
        request
        for request in REQUESTS
        if (not status_filter or request.current_status == status_filter.lower())
        and (not request_date or parse_iso_datetime(request.created_at).date() == request_date)
        and (not username or request.username == username)
    ]
    filtered_items.sort(
        key=lambda item: item.updated_at or item.created_at,
        reverse=True,
    )
    items = filtered_items[start_index:end_index]
    return AdminRequestList(
        items=items,
        source="memory-fallback",
        limit=page_size,
        table=table,
        page=page,
        page_size=page_size,
        returned=len(items),
        has_next=len(filtered_items) > end_index,
        updated_at=app_now().isoformat(),
    )


@app.delete("/api/admin/request-history", response_model=RequestHistoryClearResponse)
def clear_admin_request_history(
    _: UserPublic = Depends(require_roles("admin")),
) -> RequestHistoryClearResponse:
    cleared_memory_items = (
        len(REQUESTS)
        + len(PREDICTIONS)
        + len(REQUEST_INPUTS)
        + len(REQUEST_LATENCIES_MS)
    )
    REQUESTS.clear()
    PREDICTIONS.clear()
    REQUEST_INPUTS.clear()
    REQUEST_LATENCIES_MS.clear()

    truncated_tables: list[str] = []
    reader = get_cassandra_reader()
    if reader:
        truncated_tables = reader.clear_request_history()

    return RequestHistoryClearResponse(
        status="ok",
        truncated_tables=truncated_tables,
        cleared_memory_items=cleared_memory_items,
        updated_at=app_now().isoformat(),
    )


@app.delete("/api/admin/requests/{request_id}", response_model=RequestDeleteResponse)
def delete_admin_request(
    request_id: str,
    protein_id: str | None = Query(default=None),
    username: str | None = Query(default=None),
    source: str | None = Query(default=None),
    created_at: str | None = Query(default=None),
    updated_at: str | None = Query(default=None),
    current_status: str | None = Query(default=None),
    stage_name: str | None = Query(default=None),
    model_version: str | None = Query(default=None),
    feature_version: str | None = Query(default=None),
    _: UserPublic = Depends(require_roles("admin")),
) -> RequestDeleteResponse:
    cleared_memory_items = delete_request_from_memory(request_id)

    deleted_tables: list[str] = []
    reader = get_cassandra_reader()
    if reader:
        fallback_row = {
            "request_id": request_id,
            "protein_id": protein_id,
            "username": username,
            "source": source,
            "created_at": created_at,
            "updated_at": updated_at,
            "current_status": current_status,
            "stage_name": stage_name,
            "model_version": model_version,
            "feature_version": feature_version,
        }
        fallback_row = {
            key: value for key, value in fallback_row.items() if value is not None
        }
        deleted_tables = reader.delete_request(request_id, fallback_row or None)

    if not deleted_tables and cleared_memory_items == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    return RequestDeleteResponse(
        status="ok",
        request_id=request_id,
        deleted_tables=deleted_tables,
        cleared_memory_items=cleared_memory_items,
        updated_at=app_now().isoformat(),
    )


@app.get("/api/proteins/{protein_id}/requests", response_model=ProteinRequestList)
def get_protein_requests(
    protein_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: UserPublic = Depends(require_roles("user", "admin")),
) -> ProteinRequestList:
    normalized_protein_id = protein_id.strip()
    if not normalized_protein_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="protein_id is required",
        )

    reader = get_cassandra_reader()
    if reader:
        try:
            rows = reader.list_requests_by_protein(normalized_protein_id, limit)
            items = [inference_request_from_row(row) for row in rows]
            return ProteinRequestList(
                protein_id=normalized_protein_id,
                items=items[:limit],
                source="cassandra",
                limit=limit,
                returned=len(items[:limit]),
                updated_at=app_now().isoformat(),
            )
        except Exception:
            pass

    items = [
        request
        for request in REQUESTS
        if request.protein_id.lower() == normalized_protein_id.lower()
    ][:limit]
    return ProteinRequestList(
        protein_id=normalized_protein_id,
        items=items,
        source="memory-fallback",
        limit=limit,
        returned=len(items),
        updated_at=app_now().isoformat(),
    )


@app.get("/api/admin/requests/{request_id}/timeline", response_model=list[RequestTimelineEvent])
def get_admin_request_timeline(
    request_id: str,
    _: UserPublic = Depends(require_roles("admin")),
) -> list[RequestTimelineEvent]:
    reader = get_cassandra_reader()
    if reader:
        try:
            return [
                RequestTimelineEvent(
                    request_id=str(row.get("request_id", request_id)),
                    event_ts=str(row.get("event_ts")),
                    event_type=str(row.get("event_type", "pipeline_event")),
                    stage_name=row.get("stage_name"),
                    status=row.get("status"),
                    message=row.get("message"),
                    latency_ms=int(row.get("latency_ms", 0) or 0),
                    payload=row.get("payload"),
                )
                for row in reader.request_timeline(request_id)
            ]
        except Exception:
            pass

    for request in REQUESTS:
        if request.request_id == request_id:
            return [
                RequestTimelineEvent(
                    request_id=request_id,
                    event_ts=request.created_at,
                    event_type="memory_request",
                    stage_name=request.stage_name,
                    status=request.current_status,
                    message=request.error_message,
                    latency_ms=REQUEST_LATENCIES_MS.get(request_id),
                )
            ]
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")


@app.get(
    "/api/proteins/{protein_id}/latest-prediction",
    response_model=LatestPrediction | None,
)
def get_latest_prediction(
    protein_id: str,
    current_user: UserPublic = Depends(require_roles("user", "admin")),
) -> LatestPrediction | None:
    for prediction in PREDICTIONS:
        if prediction.protein_id.lower() == protein_id.lower():
            if user_is_admin(current_user):
                return prediction
            request = next(
                (
                    item
                    for item in REQUESTS
                    if item.request_id == prediction.request_id
                ),
                None,
            )
            if request and request.username == current_user.username:
                return prediction
            reader = get_cassandra_reader()
            if reader:
                try:
                    row = reader.get_request(prediction.request_id)
                    if row and row.get("username") == current_user.username:
                        return prediction
                except Exception:
                    pass
            continue
    return None


def main() -> None:
    import uvicorn

    uvicorn.run(
        "apps.serving_api.src.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )


if __name__ == "__main__":
    main()
