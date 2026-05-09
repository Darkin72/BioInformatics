from __future__ import annotations

from typing import Any

from .kafka_io import json_dumps


class RabbitMQPublisher:
    def __init__(self, url: str, exchange: str):
        try:
            import pika
        except ImportError as exc:
            raise RuntimeError("Install pika to use RabbitMQPublisher") from exc

        self._pika = pika
        self._url = url
        self._exchange = exchange
        self._connect()

    def _connect(self) -> None:
        self._connection = self._pika.BlockingConnection(self._pika.URLParameters(self._url))
        self._channel = self._connection.channel()
        self._channel.exchange_declare(exchange=self._exchange, exchange_type="topic", durable=True)

    def _ensure_open(self) -> None:
        if self._connection.is_closed or self._channel.is_closed:
            self._connect()

    def declare_queue(self, queue_name: str, routing_keys: list[str]) -> None:
        self._ensure_open()
        self._channel.queue_declare(queue=queue_name, durable=True)
        for routing_key in routing_keys:
            self._channel.queue_bind(
                exchange=self._exchange,
                queue=queue_name,
                routing_key=routing_key,
            )

    def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        self._ensure_open()
        self._channel.basic_publish(
            exchange=self._exchange,
            routing_key=routing_key,
            body=json_dumps(payload).encode("utf-8"),
            properties=self._pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )

    def close(self) -> None:
        if self._connection.is_open:
            self._connection.close()
