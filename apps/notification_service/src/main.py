"""Kafka notification service with Cassandra materialized views and SSE."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from collections import Counter, deque
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse


APP_TIMEZONE = timezone(timedelta(hours=7))


def app_now() -> datetime:
    return datetime.now(APP_TIMEZONE)


def parse_ts(value: str | None) -> datetime:
    if not value:
        return app_now()
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=APP_TIMEZONE)
    return parsed.astimezone(APP_TIMEZONE)


def json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=APP_TIMEZONE)
        return value.astimezone(APP_TIMEZONE).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


@dataclass(frozen=True)
class CassandraSettings:
    host: str = os.getenv("CASSANDRA_HOST", os.getenv("CASSANDRA_HOSTS", "localhost"))
    port: int = int(os.getenv("CASSANDRA_PORT", "9042"))
    keyspace: str = os.getenv("CASSANDRA_KEYSPACE", "protein_rt")


class CassandraWriter:
    def __init__(self, settings: CassandraSettings):
        try:
            from cassandra.cluster import Cluster
        except ImportError as exc:
            raise RuntimeError("Install cassandra-driver to use CassandraWriter") from exc

        hosts = [host.strip() for host in settings.host.split(",") if host.strip()]
        self._cluster = Cluster(hosts, port=settings.port)
        self._session = self._cluster.connect(settings.keyspace)

    def close(self) -> None:
        self._cluster.shutdown()

    def write_request_status(self, event: dict[str, Any]) -> None:
        request_id = str(event["request_id"])
        protein_id = str(event.get("protein_id", ""))
        status = str(event.get("current_status", event.get("status", "processing"))).lower()
        username = str(event.get("username", "system"))
        source = str(event.get("source", "pipeline"))
        created_at = parse_ts(event.get("created_at") or event.get("event_ts"))
        updated_at = parse_ts(event.get("updated_at") or event.get("event_ts"))
        request_date = created_at.date()
        status_bucket = f"{request_date.isoformat()}#{status}"
        username_bucket = f"{request_date.isoformat()}#{username}"
        protein_bucket = protein_id.lower()
        row = (
            request_id,
            request_date,
            status_bucket,
            protein_id,
            username,
            source,
            created_at,
            updated_at,
            status,
            event.get("error_code"),
            event.get("error_message"),
            event.get("stage_name"),
            int(event.get("retry_count", 0) or 0),
            event.get("model_version"),
            event.get("feature_version"),
        )
        self._session.execute(
            """
            INSERT INTO request_status_by_id (
                request_id, request_date, status_bucket, protein_id, username, source,
                created_at, updated_at, current_status, error_code, error_message,
                stage_name, retry_count, model_version, feature_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            row,
        )
        self._session.execute(
            """
            INSERT INTO requests_by_day (
                request_date, created_at, request_id, protein_id, username, source,
                updated_at, current_status, error_code, error_message, stage_name,
                retry_count, model_version, feature_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                request_date,
                created_at,
                request_id,
                protein_id,
                username,
                source,
                updated_at,
                status,
                event.get("error_code"),
                event.get("error_message"),
                event.get("stage_name"),
                int(event.get("retry_count", 0) or 0),
                event.get("model_version"),
                event.get("feature_version"),
            ),
        )
        self._session.execute(
            """
            INSERT INTO requests_by_status_window (
                status_bucket, updated_at, request_id, request_date, protein_id, username,
                source, current_status, error_code, error_message, stage_name, retry_count,
                model_version, feature_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                status_bucket,
                updated_at,
                request_id,
                request_date,
                protein_id,
                username,
                source,
                status,
                event.get("error_code"),
                event.get("error_message"),
                event.get("stage_name"),
                int(event.get("retry_count", 0) or 0),
                event.get("model_version"),
                event.get("feature_version"),
            ),
        )
        self._session.execute(
            """
            INSERT INTO requests_by_user_window (
                username_bucket, created_at, request_id, request_date, protein_id, username,
                source, updated_at, current_status, error_code, error_message, stage_name,
                retry_count, model_version, feature_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                username_bucket,
                created_at,
                request_id,
                request_date,
                protein_id,
                username,
                source,
                updated_at,
                status,
                event.get("error_code"),
                event.get("error_message"),
                event.get("stage_name"),
                int(event.get("retry_count", 0) or 0),
                event.get("model_version"),
                event.get("feature_version"),
            ),
        )
        self._session.execute(
            """
            INSERT INTO requests_by_protein_window (
                protein_bucket, created_at, request_id, request_date, protein_id, username,
                source, updated_at, current_status, error_code, error_message, stage_name,
                retry_count, model_version, feature_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                protein_bucket,
                created_at,
                request_id,
                request_date,
                protein_id,
                username,
                source,
                updated_at,
                status,
                event.get("error_code"),
                event.get("error_message"),
                event.get("stage_name"),
                int(event.get("retry_count", 0) or 0),
                event.get("model_version"),
                event.get("feature_version"),
            ),
        )
        self.write_timeline(
            request_id=request_id,
            event_ts=updated_at,
            event_type="request_status",
            stage_name=event.get("stage_name"),
            status=status,
            message=event.get("error_message"),
            latency_ms=event.get("latency_ms"),
            payload=event,
        )

    def write_prediction(self, event: dict[str, Any]) -> None:
        protein_id = str(event["protein_id"])
        request_id = str(event["request_id"])
        predicted_at = parse_ts(event.get("predicted_at") or event.get("event_ts"))
        top_terms_payload = event.get("top_terms", [])
        top_terms: list[str] = []
        top_scores: list[float] = []
        for item in top_terms_payload:
            if isinstance(item, dict):
                top_terms.append(str(item.get("term_id", item.get("go_term", ""))))
                top_scores.append(float(item.get("score", 0)))
            else:
                top_terms.append(str(item))
        self._session.execute(
            """
            INSERT INTO latest_prediction_by_protein (
                protein_id, request_id, predicted_at, model_version, top_terms,
                top_scores, confidence_summary
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                protein_id,
                request_id,
                predicted_at,
                event.get("model_version"),
                top_terms,
                top_scores,
                event.get("confidence_summary"),
            ),
        )
        self._session.execute(
            """
            INSERT INTO prediction_history_by_protein (
                protein_id, predicted_at, request_id, model_version, feature_version,
                top_terms, top_scores, confidence_summary, latency_ms
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                protein_id,
                predicted_at,
                request_id,
                event.get("model_version"),
                event.get("feature_version"),
                top_terms,
                top_scores,
                event.get("confidence_summary"),
                int(event.get("latency_ms", 0) or 0),
            ),
        )
        self.write_timeline(
            request_id=request_id,
            event_ts=predicted_at,
            event_type="prediction_result",
            stage_name="prediction_written",
            status="completed",
            message=event.get("confidence_summary"),
            latency_ms=event.get("latency_ms"),
            payload=event,
        )

    def write_metric(
        self,
        metric_name: str,
        window_start: datetime,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        window_end = window_start + timedelta(minutes=1)
        self._session.execute(
            """
            INSERT INTO pipeline_metrics_by_window (
                metric_date, metric_name, window_start, window_end, metric_value, tags
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (window_start.date(), metric_name, window_start, window_end, value, tags or {}),
        )

    def write_stat(self, stat_name: str, value: float, detail: str) -> None:
        now = app_now()
        self._session.execute(
            """
            INSERT INTO cassandra_serving_stats_by_day (
                stat_date, stat_name, updated_at, stat_value, detail
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (now.date(), stat_name, now, value, detail),
        )

    def write_timeline(
        self,
        request_id: str,
        event_ts: datetime,
        event_type: str,
        stage_name: Any,
        status: str | None,
        message: Any,
        latency_ms: Any,
        payload: dict[str, Any],
    ) -> None:
        self._session.execute(
            """
            INSERT INTO request_timeline_by_id (
                request_id, event_ts, event_type, stage_name, status, message,
                latency_ms, payload
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                request_id,
                event_ts,
                event_type,
                stage_name,
                status,
                message,
                int(latency_ms or 0),
                json.dumps(payload, default=json_default),
            ),
        )


class Broadcaster:
    def __init__(self) -> None:
        self._clients: set[queue.Queue[str]] = set()
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue[str]:
        client: queue.Queue[str] = queue.Queue(maxsize=100)
        with self._lock:
            self._clients.add(client)
        return client

    def unsubscribe(self, client: queue.Queue[str]) -> None:
        with self._lock:
            self._clients.discard(client)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        message = (
            f"event: {event_type}\n"
            f"data: {json.dumps(payload, default=json_default)}\n\n"
        )
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            try:
                client.put_nowait(message)
            except queue.Full:
                pass


class MetricAggregator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status_counts: Counter[str] = Counter()
        self._latencies: deque[int] = deque(maxlen=5000)
        self._throughput: Counter[datetime] = Counter()
        self._error_codes: Counter[str] = Counter()
        self._writes_by_table: Counter[str] = Counter()
        self._last_event_at: datetime | None = None

    def record(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = app_now()
        minute = now.replace(second=0, microsecond=0)
        with self._lock:
            self._last_event_at = now
            self._throughput[minute] += 1
            if event_type == "request_status":
                status = str(payload.get("current_status", "processing")).lower()
                self._status_counts[status] += 1
                self._writes_by_table.update(
                    [
                        "request_status_by_id",
                        "requests_by_day",
                        "requests_by_status_window",
                        "requests_by_user_window",
                        "request_timeline_by_id",
                    ]
                )
                if payload.get("error_code"):
                    self._error_codes[str(payload["error_code"])] += 1
            if event_type == "prediction_result":
                self._writes_by_table.update(
                    [
                        "latest_prediction_by_protein",
                        "prediction_history_by_protein",
                        "request_timeline_by_id",
                    ]
                )
            if payload.get("latency_ms") is not None:
                self._latencies.append(int(payload.get("latency_ms") or 0))
            return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        values = sorted(self._latencies)
        avg = round(sum(values) / len(values)) if values else 0
        p95 = values[min(len(values) - 1, round((len(values) - 1) * 0.95))] if values else 0
        recent_minutes = []
        now_minute = app_now().replace(second=0, microsecond=0)
        for index in range(8):
            start = now_minute - timedelta(minutes=7 - index)
            recent_minutes.append(
                {
                    "window_start": start.isoformat(),
                    "window_end": (start + timedelta(minutes=1)).isoformat(),
                    "metric_name": "events_per_minute",
                    "metric_value": self._throughput[start],
                    "tags": {"source": "notification_service"},
                }
            )
        return {
            "updated_at": app_now().isoformat(),
            "avg_latency_ms": avg,
            "p95_latency_ms": p95,
            "throughput": recent_minutes,
            "status_counts": dict(self._status_counts),
            "error_codes": dict(self._error_codes.most_common(8)),
            "cassandra": {
                "write_tables": dict(self._writes_by_table),
                "active_query_patterns": [
                    "request_status_by_id",
                    "requests_by_day",
                    "requests_by_status_window",
                    "requests_by_user_window",
                    "prediction_history_by_protein",
                    "pipeline_metrics_by_window",
                ],
                "last_event_at": self._last_event_at.isoformat() if self._last_event_at else None,
            },
        }


app = FastAPI(title="Protein Notification Service")
broadcaster = Broadcaster()
aggregator = MetricAggregator()

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


def handle_event(writer: CassandraWriter | None, event_type: str, payload: dict[str, Any]) -> None:
    snapshot = aggregator.record(event_type, payload)
    write_error: Exception | None = None

    if writer:
        try:
            if event_type == "request_status":
                writer.write_request_status(payload)
            elif event_type == "prediction_result":
                writer.write_prediction(payload)
                writer.write_request_status({**payload, "current_status": "completed"})
            elif event_type == "dead_letter":
                writer.write_request_status({**payload, "current_status": "failed"})

            now_minute = app_now().replace(second=0, microsecond=0)
            writer.write_metric(
                "events_per_minute",
                now_minute,
                snapshot["throughput"][-1]["metric_value"],
            )
            writer.write_stat(
                "materialized_writes",
                float(sum(snapshot["cassandra"]["write_tables"].values())),
                "Denormalized writes across Cassandra serving tables",
            )
        except Exception as exc:
            write_error = exc

    broadcaster.publish(event_type, payload)
    broadcaster.publish("dashboard_snapshot", snapshot)
    if write_error:
        broadcaster.publish("service_warning", {"message": f"Cassandra write failed: {write_error}"})


def consume_kafka(stop_event: threading.Event) -> None:
    try:
        from kafka import KafkaConsumer
    except ImportError:
        broadcaster.publish("service_warning", {"message": "kafka-python is not installed"})
        return

    writer: CassandraWriter | None = None
    try:
        writer = CassandraWriter(CassandraSettings())
    except Exception as exc:
        broadcaster.publish("service_warning", {"message": f"Cassandra unavailable: {exc}"})

    topics = [
        os.getenv("KAFKA_REQUEST_STATUS_TOPIC", "request_status"),
        os.getenv("KAFKA_PREDICTION_TOPIC", "prediction_result"),
        os.getenv("KAFKA_DEAD_LETTER_TOPIC", "dead_letter"),
    ]
    while not stop_event.is_set():
        try:
            consumer = KafkaConsumer(
                *topics,
                bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
                group_id=os.getenv("NOTIFICATION_CONSUMER_GROUP", "protein-notification-service"),
                auto_offset_reset="latest",
                enable_auto_commit=True,
                value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
            )
            for message in consumer:
                if stop_event.is_set():
                    break
                topic = message.topic
                event_type = {
                    os.getenv("KAFKA_REQUEST_STATUS_TOPIC", "request_status"): "request_status",
                    os.getenv("KAFKA_PREDICTION_TOPIC", "prediction_result"): "prediction_result",
                    os.getenv("KAFKA_DEAD_LETTER_TOPIC", "dead_letter"): "dead_letter",
                }.get(topic, "pipeline_event")
                if isinstance(message.value, dict):
                    handle_event(writer, event_type, message.value)
        except Exception as exc:
            broadcaster.publish("service_warning", {"message": f"Kafka consumer retrying: {exc}"})
            time.sleep(5)

    if writer:
        writer.close()


stop_event = threading.Event()
consumer_thread: threading.Thread | None = None


@app.on_event("startup")
def startup() -> None:
    global consumer_thread
    consumer_thread = threading.Thread(target=consume_kafka, args=(stop_event,), daemon=True)
    consumer_thread.start()


@app.on_event("shutdown")
def shutdown() -> None:
    stop_event.set()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/events/dashboard")
def dashboard_events() -> StreamingResponse:
    client = broadcaster.subscribe()

    def stream() -> Iterator[str]:
        try:
            yield (
                "event: dashboard_snapshot\n"
                f"data: {json.dumps(aggregator.snapshot(), default=json_default)}\n\n"
            )
            while True:
                try:
                    yield client.get(timeout=20)
                except queue.Empty:
                    yield "event: heartbeat\ndata: {}\n\n"
        finally:
            broadcaster.unsubscribe(client)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/metrics/live")
def live_metrics() -> dict[str, Any]:
    return aggregator.snapshot()
