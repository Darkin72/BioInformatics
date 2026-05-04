"""Serving API with JWT authentication and role-based authorization."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from apps.serving_api.src.cafa6_client import (
    Cafa6AnalysisError,
    Cafa6ValidationError,
    run_cafa6_analysis,
)

JWT_ALGORITHM = "HS256"
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
JWT_EXPIRES_SECONDS = int(os.getenv("JWT_EXPIRES_SECONDS", "3600"))

Role = str


class LoginRequest(BaseModel):
    username: str
    password: str


class UserPublic(BaseModel):
    username: str
    display_name: str
    roles: list[Role]


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


class InferenceRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    request_id: str
    protein_id: str
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


class LatestPrediction(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    protein_id: str
    request_id: str
    predicted_at: str
    model_version: str
    top_terms: list[PredictionTerm]
    confidence_summary: str | None = None


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
    recent_predictions: list[LatestPrediction]
    recent_failed_requests: list[InferenceRequest]
    updated_at: str


security = HTTPBearer()
app = FastAPI(title="BioInformatics Serving API")
REVOKED_TOKEN_IDS: set[str] = set()

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


USERS = {
    "viewer": {
        "password_hash": hash_password("viewer123"),
        "display_name": "Viewer",
        "roles": ["viewer"],
    },
    "operator": {
        "password_hash": hash_password("operator123"),
        "display_name": "Pipeline Operator",
        "roles": ["viewer", "operator"],
    },
    "admin": {
        "password_hash": hash_password("admin123"),
        "display_name": "Admin",
        "roles": ["viewer", "operator", "admin"],
    },
}

REQUESTS: list[InferenceRequest] = []
PREDICTIONS: list[LatestPrediction] = []
REQUEST_LATENCIES_MS: dict[str, int] = {}


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
        display_name=str(user["display_name"]),
        roles=list(user["roles"]),
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


def build_throughput() -> list[PipelineMetricPoint]:
    now = utc_now()
    points: list[PipelineMetricPoint] = []
    for index in range(8):
        start = now - timedelta(minutes=(7 - index) * 5)
        end = start + timedelta(minutes=5)
        value = sum(
            1
            for request in REQUESTS
            if start <= datetime.fromisoformat(request.created_at) < end
        )
        points.append(
            PipelineMetricPoint(
                window_start=start.isoformat(),
                window_end=end.isoformat(),
                metric_name="throughput_per_minute",
                metric_value=value,
                tags={"source": "cafa6_modal_endpoint"},
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
    return datetime.fromisoformat(iso_timestamp).date() == utc_now().date()


def latest_predictions(limit: int = 10) -> list[LatestPrediction]:
    return sorted(PREDICTIONS, key=lambda item: item.predicted_at, reverse=True)[:limit]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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


@app.post("/api/auth/logout")
def logout(payload: dict[str, Any] = Depends(get_current_token_payload)) -> dict[str, str]:
    token_id = payload.get("jti")
    if isinstance(token_id, str):
        REVOKED_TOKEN_IDS.add(token_id)
    return {"status": "ok"}


@app.get("/api/auth/me", response_model=UserPublic)
def me(current_user: UserPublic = Depends(get_current_user)) -> UserPublic:
    return current_user


@app.get("/api/metrics/pipeline/summary", response_model=DashboardSummary)
def get_pipeline_summary(
    window: str = Query(default="minute"),
    _: UserPublic = Depends(require_roles("viewer", "operator", "admin")),
) -> DashboardSummary:
    status_counts = {
        "pending": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0,
        "retrying": 0,
        "cancelled": 0,
    }
    for request in REQUESTS:
        status_counts[request.current_status] = (
            status_counts.get(request.current_status, 0) + 1
        )

    total_today = sum(1 for request in REQUESTS if is_today(request.created_at))
    failed_count = status_counts.get("failed", 0)
    error_rate = failed_count / len(REQUESTS) if REQUESTS else 0
    avg_latency_ms, p95_latency_ms = calculate_latency_ms()
    return DashboardSummary(
        total_today=total_today,
        status_counts=status_counts,
        avg_latency_ms=avg_latency_ms,
        p95_latency_ms=p95_latency_ms,
        error_rate=round(error_rate, 4),
        throughput=build_throughput(),
        recent_predictions=latest_predictions(),
        recent_failed_requests=[
            request for request in REQUESTS if request.current_status == "failed"
        ],
        updated_at=utc_now().isoformat(),
    )


@app.post(
    "/api/inference-requests",
    response_model=InferenceRequest,
    status_code=status.HTTP_201_CREATED,
)
def create_inference_request(
    payload: CreateInferenceRequestPayload,
    _: UserPublic = Depends(require_roles("operator", "admin")),
) -> InferenceRequest:
    request_id = f"api-{uuid.uuid4()}"
    created_at = utc_now().isoformat()
    protein_id = payload.protein_id.strip()

    if not protein_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="protein_id is required",
        )

    try:
        analysis = run_cafa6_analysis(protein_id=protein_id, sequence=payload.sequence)
    except Cafa6ValidationError as exc:
        failed = InferenceRequest(
            request_id=request_id,
            protein_id=protein_id,
            created_at=created_at,
            updated_at=utc_now().isoformat(),
            current_status="failed",
            stage_name="validation",
            error_code="INVALID_SEQUENCE",
            error_message=str(exc),
            retry_count=0,
        )
        REQUESTS.insert(0, failed)
        return failed
    except Cafa6AnalysisError as exc:
        failed = InferenceRequest(
            request_id=request_id,
            protein_id=protein_id,
            created_at=created_at,
            updated_at=utc_now().isoformat(),
            current_status="failed",
            stage_name="external_analysis",
            error_code="ANALYSIS_API_ERROR",
            error_message=str(exc),
            retry_count=0,
        )
        REQUESTS.insert(0, failed)
        return failed

    created = InferenceRequest(
        request_id=request_id,
        protein_id=protein_id,
        created_at=created_at,
        updated_at=utc_now().isoformat(),
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
        predicted_at=created.updated_at or utc_now().isoformat(),
        model_version=analysis.model_version,
        top_terms=[
            PredictionTerm(
                term_id=term.term_id,
                term_name=term.term_name,
                ontology=term.ontology,
                score=term.score,
            )
            for term in analysis.top_terms
        ],
        confidence_summary=analysis.confidence_summary,
    )
    PREDICTIONS.insert(0, prediction)
    return created


@app.get("/api/inference-requests/{request_id}", response_model=InferenceRequest)
def get_inference_request(
    request_id: str,
    _: UserPublic = Depends(require_roles("viewer", "operator", "admin")),
) -> InferenceRequest:
    for request in REQUESTS:
        if request.request_id == request_id:
            return request

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Request not found",
    )


@app.get(
    "/api/proteins/{protein_id}/latest-prediction",
    response_model=LatestPrediction | None,
)
def get_latest_prediction(
    protein_id: str,
    _: UserPublic = Depends(require_roles("viewer", "operator", "admin")),
) -> LatestPrediction | None:
    for prediction in PREDICTIONS:
        if prediction.protein_id.lower() == protein_id.lower():
            return prediction
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
