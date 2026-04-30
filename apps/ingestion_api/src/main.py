from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError

from libs.protein_rt.cassandra_store import CassandraStore
from libs.protein_rt.config import CassandraConfig, KafkaConfig, RabbitMQConfig
from libs.protein_rt.events import RawProteinInputEvent
from libs.protein_rt.kafka_io import KafkaJsonProducer
from libs.protein_rt.rabbitmq import RabbitMQPublisher


app = FastAPI(title="Protein Realtime Ingestion API", version="0.1.0")
logger = logging.getLogger(__name__)


class ProteinIngestRequest(BaseModel):
    protein_id: str
    sequence: str
    source: str = "api"
    top_k: int | None = Field(default=None, ge=1, le=500)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProteinIngestResponse(BaseModel):
    request_id: str
    protein_id: str
    status: str
    kafka_topic: str


class AppState:
    kafka: KafkaJsonProducer | None = None
    rabbitmq: RabbitMQPublisher | None = None
    cassandra: CassandraStore | None = None


state = AppState()


@app.on_event("startup")
def startup() -> None:
    kafka_config = KafkaConfig()
    rabbit_config = RabbitMQConfig()
    state.kafka = KafkaJsonProducer(kafka_config.bootstrap_servers)
    state.rabbitmq = RabbitMQPublisher(rabbit_config.url, rabbit_config.exchange)
    state.cassandra = CassandraStore(CassandraConfig())


@app.on_event("shutdown")
def shutdown() -> None:
    if state.kafka:
        state.kafka.flush()
    if state.rabbitmq:
        state.rabbitmq.close()
    if state.cassandra:
        state.cassandra.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/proteins", response_model=ProteinIngestResponse, status_code=202)
def ingest_protein(payload: ProteinIngestRequest) -> ProteinIngestResponse:
    if state.kafka is None or state.cassandra is None:
        raise HTTPException(status_code=503, detail="ingestion dependencies are not initialized")

    try:
        metadata = dict(payload.metadata)
        if payload.top_k is not None:
            metadata["top_k"] = payload.top_k
        if payload.threshold is not None:
            metadata["threshold"] = payload.threshold
        event = RawProteinInputEvent(
            protein_id=payload.protein_id,
            sequence=payload.sequence,
            source=payload.source,
            metadata=metadata,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    kafka_config = KafkaConfig()
    state.cassandra.put_raw_event(event)
    state.cassandra.put_request_status(
        request_id=event.request_id,
        protein_id=event.protein_id,
        status="ACCEPTED",
        stage_name="ingestion_api",
    )
    state.kafka.send(kafka_config.raw_topic, key=event.protein_id, value=event)

    if state.rabbitmq:
        try:
            state.rabbitmq.publish(
                "request.accepted",
                {
                    "request_id": event.request_id,
                    "protein_id": event.protein_id,
                    "status": "ACCEPTED",
                },
            )
        except Exception:
            logger.exception("RabbitMQ control event publish failed; ingestion event was accepted")

    return ProteinIngestResponse(
        request_id=event.request_id,
        protein_id=event.protein_id,
        status="ACCEPTED",
        kafka_topic=kafka_config.raw_topic,
    )


def main() -> None:
    import uvicorn

    uvicorn.run("apps.ingestion_api.src.main:app", host="0.0.0.0", port=8001)


if __name__ == "__main__":
    main()
