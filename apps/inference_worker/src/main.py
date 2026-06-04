from __future__ import annotations

import json
import os
import time
from typing import Any

from apps.serving_api.src.main import (
    RequestInputRecord,
    batch_protein_label,
    process_cafa6_streaming_request,
)
from libs.protein_rt.config import RabbitMQConfig


def records_from_payload(payload: dict[str, Any]) -> list[RequestInputRecord]:
    records: list[RequestInputRecord] = []
    for item in payload.get("records") or []:
        if not isinstance(item, dict):
            continue
        protein_id = str(item.get("protein_id") or item.get("id") or "").strip()
        if not protein_id:
            continue
        sequence = item.get("sequence")
        sequence_text = str(sequence) if sequence is not None else None
        sequence_length = item.get("sequence_length")
        records.append(
            RequestInputRecord(
                protein_id=protein_id,
                sequence=sequence_text,
                sequence_length=(
                    int(sequence_length)
                    if sequence_length is not None
                    else len(sequence_text)
                    if sequence_text is not None
                    else None
                ),
                description=(
                    str(item["description"])
                    if item.get("description") is not None
                    else None
                ),
            )
        )
    if not records:
        raise ValueError("inference job does not contain records")
    return records


class InferenceWorker:
    def __init__(self) -> None:
        try:
            import pika
        except ImportError as exc:
            raise RuntimeError("Install pika to run inference worker") from exc

        self._pika = pika
        self._rabbit_config = RabbitMQConfig()
        parameters = pika.URLParameters(self._rabbit_config.url)
        parameters.heartbeat = int(os.getenv("INFERENCE_WORKER_RABBITMQ_HEARTBEAT", "0"))
        parameters.blocked_connection_timeout = int(
            os.getenv("INFERENCE_WORKER_BLOCKED_CONNECTION_TIMEOUT", "1800")
        )
        self._connection = pika.BlockingConnection(parameters)
        self._channel = self._connection.channel()
        self._channel.exchange_declare(
            exchange=self._rabbit_config.exchange,
            exchange_type="topic",
            durable=True,
        )
        self._channel.queue_declare(queue=self._rabbit_config.inference_queue, durable=True)
        self._channel.queue_bind(
            exchange=self._rabbit_config.exchange,
            queue=self._rabbit_config.inference_queue,
            routing_key="inference.submit",
        )

    def close(self) -> None:
        if self._connection.is_open:
            self._connection.close()

    def handle(self, channel: Any, method: Any, _properties: Any, body: bytes) -> None:
        try:
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("inference job payload must be a JSON object")

            records = records_from_payload(payload)
            request_id = str(payload["request_id"])
            protein_id = str(payload.get("protein_id") or batch_protein_label(records))
            source = str(payload.get("source") or "serving_api")
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            combined_sequence = "\n".join(record.sequence or "" for record in records)

            process_cafa6_streaming_request(
                request_id=request_id,
                protein_id=protein_id,
                username=str(payload.get("username") or "system"),
                source=source,
                sequence=combined_sequence,
                model_name=str(payload.get("model_name") or metadata.get("model") or "ensemble"),
                top_k=(
                    int(payload["top_k"])
                    if payload.get("top_k") is not None
                    else None
                ),
                threshold=(
                    float(payload["threshold"])
                    if payload.get("threshold") is not None
                    else None
                ),
                metadata=metadata,
                created_at=str(payload["created_at"]),
                retry_count=int(payload.get("retry_count", 0) or 0),
                records=records,
            )
            channel.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as exc:
            print(f"inference_worker failed: {type(exc).__name__}: {exc}", flush=True)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def run(self) -> None:
        prefetch_count = int(os.getenv("INFERENCE_WORKER_PREFETCH", "1"))
        self._channel.basic_qos(prefetch_count=max(1, prefetch_count))
        self._channel.basic_consume(
            queue=self._rabbit_config.inference_queue,
            on_message_callback=self.handle,
        )
        print(
            f"inference_worker consuming {self._rabbit_config.inference_queue}",
            flush=True,
        )
        self._channel.start_consuming()


def main() -> None:
    worker = InferenceWorker()
    try:
        worker.run()
    finally:
        time.sleep(0.1)
        worker.close()


if __name__ == "__main__":
    main()
