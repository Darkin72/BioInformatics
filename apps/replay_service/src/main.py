from __future__ import annotations

import random
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from libs.protein_rt.cassandra_store import CassandraStore
from libs.protein_rt.config import CassandraConfig, KafkaConfig, RabbitMQConfig
from libs.protein_rt.events import RawProteinInputEvent
from libs.protein_rt.kafka_io import KafkaJsonProducer
from libs.protein_rt.rabbitmq import RabbitMQPublisher

app = FastAPI(title="CAFA-6 Replay Service", version="0.1.0")


class ReplayStartRequest(BaseModel):
    fasta_path: str
    source: str = "cafa6_replay"
    records_per_second: float = Field(default=2.0, gt=0, le=200)
    max_records: int | None = Field(default=None, ge=1)
    top_k: int | None = Field(default=None, ge=1, le=500)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    inject_error_every: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplayStatus(BaseModel):
    campaign_id: str | None = None
    state: str
    emitted: int
    accepted: int
    failed: int
    total_records: int | None = None
    current_protein_id: str | None = None
    error: str | None = None


class ReplayState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.status = ReplayStatus(state="idle", emitted=0, accepted=0, failed=0)

    def snapshot(self) -> ReplayStatus:
        with self.lock:
            return self.status.model_copy()

    def update(self, **changes: Any) -> None:
        with self.lock:
            self.status = self.status.model_copy(update=changes)


state = ReplayState()


def parse_fasta(path: Path) -> list[tuple[str, str]]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"FASTA file not found: {path}")

    records: list[tuple[str, str]] = []
    current_id: str | None = None
    sequence_parts: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if current_id and sequence_parts:
                records.append((current_id, "".join(sequence_parts)))
            current_id = line[1:].split()[0].strip() or f"protein_{len(records) + 1}"
            sequence_parts = []
        else:
            sequence_parts.append(line)
    if current_id and sequence_parts:
        records.append((current_id, "".join(sequence_parts)))
    if not records:
        raise ValueError("FASTA file contains no records.")
    return records


def emit_replay(payload: ReplayStartRequest, campaign_id: str) -> None:
    kafka_config = KafkaConfig()
    rabbit_config = RabbitMQConfig()
    producer: KafkaJsonProducer | None = None
    rabbit: RabbitMQPublisher | None = None
    store: CassandraStore | None = None
    try:
        records = parse_fasta(Path(payload.fasta_path))
        if payload.max_records:
            records = records[: payload.max_records]
        state.update(state="running", total_records=len(records), error=None)

        producer = KafkaJsonProducer(kafka_config.bootstrap_servers)
        rabbit = RabbitMQPublisher(rabbit_config.url, rabbit_config.exchange)
        rabbit.declare_queue(rabbit_config.notification_queue, ["request.*"])
        store = CassandraStore(CassandraConfig())
        delay_seconds = 1.0 / payload.records_per_second

        for index, (protein_id, sequence) in enumerate(records, start=1):
            if state.stop_event.is_set():
                state.update(state="stopped")
                return
            while state.pause_event.is_set():
                state.update(state="paused")
                if state.stop_event.wait(0.2):
                    state.update(state="stopped")
                    return
            state.update(state="running", current_protein_id=protein_id)

            if payload.inject_error_every and index % payload.inject_error_every == 0:
                sequence = f"{sequence}*"

            metadata = {
                **payload.metadata,
                "campaign_id": campaign_id,
                "replay_index": index,
                "producer_id": "replay_service",
            }
            if payload.top_k is not None:
                metadata["top_k"] = payload.top_k
            if payload.threshold is not None:
                metadata["threshold"] = payload.threshold

            try:
                event = RawProteinInputEvent(
                    protein_id=protein_id,
                    sequence=sequence,
                    source=payload.source,
                    metadata=metadata,
                )
                store.put_raw_event(event)
                store.put_request_status(
                    request_id=event.request_id,
                    protein_id=event.protein_id,
                    status="ACCEPTED",
                    stage_name="replay_service",
                )
                producer.send(kafka_config.raw_topic, key=event.protein_id, value=event)
                rabbit.publish(
                    "request.accepted",
                    {
                        "request_id": event.request_id,
                        "protein_id": event.protein_id,
                        "campaign_id": campaign_id,
                        "source": payload.source,
                    },
                )
                snapshot = state.snapshot()
                state.update(emitted=snapshot.emitted + 1, accepted=snapshot.accepted + 1)
            except Exception as exc:
                snapshot = state.snapshot()
                state.update(emitted=snapshot.emitted + 1, failed=snapshot.failed + 1, error=str(exc))

            jitter = random.uniform(0, delay_seconds * 0.15)
            if state.stop_event.wait(delay_seconds + jitter):
                state.update(state="stopped")
                return

        state.update(state="completed", current_protein_id=None)
    except Exception as exc:
        state.update(state="failed", error=str(exc))
    finally:
        if producer:
            producer.flush()
        if rabbit:
            rabbit.close()
        if store:
            store.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/replay/status", response_model=ReplayStatus)
def replay_status() -> ReplayStatus:
    return state.snapshot()


@app.post("/v1/replay/start", response_model=ReplayStatus, status_code=202)
def start_replay(payload: ReplayStartRequest) -> ReplayStatus:
    snapshot = state.snapshot()
    if snapshot.state in {"running", "paused"}:
        raise HTTPException(status_code=409, detail="A replay campaign is already active.")

    campaign_id = f"replay-{uuid.uuid4()}"
    state.pause_event.clear()
    state.stop_event.clear()
    state.update(
        campaign_id=campaign_id,
        state="starting",
        emitted=0,
        accepted=0,
        failed=0,
        total_records=None,
        current_protein_id=None,
        error=None,
    )
    state.thread = threading.Thread(target=emit_replay, args=(payload, campaign_id), daemon=True)
    state.thread.start()
    return state.snapshot()


@app.post("/v1/replay/pause", response_model=ReplayStatus)
def pause_replay() -> ReplayStatus:
    state.pause_event.set()
    state.update(state="paused")
    return state.snapshot()


@app.post("/v1/replay/resume", response_model=ReplayStatus)
def resume_replay() -> ReplayStatus:
    state.pause_event.clear()
    state.update(state="running")
    return state.snapshot()


@app.post("/v1/replay/stop", response_model=ReplayStatus)
def stop_replay() -> ReplayStatus:
    state.stop_event.set()
    state.pause_event.clear()
    state.update(state="stopping")
    return state.snapshot()


def main() -> None:
    import uvicorn

    uvicorn.run("apps.replay_service.src.main:app", host="0.0.0.0", port=8005)


if __name__ == "__main__":
    main()
