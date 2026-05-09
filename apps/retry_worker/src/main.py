from __future__ import annotations

import json
import time
from typing import Any

from libs.protein_rt.cassandra_store import CassandraStore
from libs.protein_rt.config import CassandraConfig, KafkaConfig, RabbitMQConfig
from libs.protein_rt.events import RawProteinInputEvent
from libs.protein_rt.kafka_io import KafkaJsonProducer


def retry_payload_to_event(payload: dict[str, Any]) -> RawProteinInputEvent:
    raw_event = payload.get("raw_event") or payload.get("payload") or payload
    if not isinstance(raw_event, dict):
        raise ValueError("retry payload must include a raw_event object")

    metadata = dict(raw_event.get("metadata") or {})
    metadata["retry_count"] = int(payload.get("retry_count", metadata.get("retry_count", 0)) or 0)
    metadata["retry_source"] = payload.get("source", "retry_worker")
    return RawProteinInputEvent(
        request_id=str(raw_event.get("request_id") or payload.get("request_id")),
        protein_id=str(raw_event.get("protein_id") or payload.get("protein_id")),
        sequence=str(raw_event.get("sequence") or raw_event.get("sequence_raw") or ""),
        source=str(raw_event.get("source") or payload.get("source") or "retry_worker"),
        metadata=metadata,
        checksum=raw_event.get("checksum"),
    )


class RetryWorker:
    def __init__(self) -> None:
        try:
            import pika
        except ImportError as exc:
            raise RuntimeError("Install pika to run retry worker") from exc

        self._pika = pika
        self._rabbit_config = RabbitMQConfig()
        self._kafka_config = KafkaConfig()
        self._connection = pika.BlockingConnection(pika.URLParameters(self._rabbit_config.url))
        self._channel = self._connection.channel()
        self._channel.exchange_declare(
            exchange=self._rabbit_config.exchange,
            exchange_type="topic",
            durable=True,
        )
        self._channel.queue_declare(queue=self._rabbit_config.retry_queue, durable=True)
        self._channel.queue_bind(
            exchange=self._rabbit_config.exchange,
            queue=self._rabbit_config.retry_queue,
            routing_key="request.retry",
        )
        self._producer = KafkaJsonProducer(self._kafka_config.bootstrap_servers)
        self._store: CassandraStore | None = None

    def close(self) -> None:
        self._producer.flush()
        if self._store:
            self._store.close()
        if self._connection.is_open:
            self._connection.close()

    def store(self) -> CassandraStore | None:
        if self._store:
            return self._store
        try:
            self._store = CassandraStore(CassandraConfig())
        except Exception as exc:
            print(f"retry_worker Cassandra unavailable: {type(exc).__name__}: {exc}")
            return None
        return self._store

    def handle(self, _channel: Any, method: Any, _properties: Any, body: bytes) -> None:
        try:
            payload = json.loads(body.decode("utf-8"))
            event = retry_payload_to_event(payload)
            retry_count = int(event.metadata.get("retry_count", 0) or 0)
            store = self.store()
            if store:
                store.put_request_status(
                    request_id=event.request_id,
                    protein_id=event.protein_id,
                    status="RETRYING",
                    stage_name="retry_worker",
                    retry_count=retry_count,
                )
            self._producer.send(self._kafka_config.raw_topic, key=event.protein_id, value=event)
            _channel.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as exc:
            print(f"retry_worker failed: {type(exc).__name__}: {exc}")
            _channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def run(self) -> None:
        self._channel.basic_qos(prefetch_count=8)
        self._channel.basic_consume(
            queue=self._rabbit_config.retry_queue,
            on_message_callback=self.handle,
        )
        print(f"retry_worker consuming {self._rabbit_config.retry_queue}")
        self._channel.start_consuming()


def main() -> None:
    worker = RetryWorker()
    try:
        worker.run()
    finally:
        time.sleep(0.1)
        worker.close()


if __name__ == "__main__":
    main()
