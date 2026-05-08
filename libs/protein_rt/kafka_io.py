from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


def json_dumps(payload: dict[str, Any] | BaseModel) -> str:
    if isinstance(payload, BaseModel):
        return payload.model_dump_json()
    return json.dumps(payload, separators=(",", ":"), default=str)


class KafkaJsonProducer:
    def __init__(self, bootstrap_servers: str):
        try:
            from kafka import KafkaProducer
        except ImportError as exc:
            raise RuntimeError("Install kafka-python to use KafkaJsonProducer") from exc

        self._producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            key_serializer=lambda value: value.encode("utf-8"),
            value_serializer=lambda value: json_dumps(value).encode("utf-8"),
            acks="all",
            retries=5,
            linger_ms=10,
        )

    def send(self, topic: str, key: str, value: dict[str, Any] | BaseModel) -> None:
        future = self._producer.send(topic, key=key, value=value)
        future.get(timeout=30)

    def flush(self) -> None:
        self._producer.flush()

