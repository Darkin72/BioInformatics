from __future__ import annotations

import os
from dataclasses import dataclass


def env(name: str, default: str) -> str:
    return os.getenv(name, default)


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class KafkaConfig:
    bootstrap_servers: str = env("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    raw_topic: str = env("KAFKA_RAW_INPUT_TOPIC", "protein.raw-input.v1")
    validated_topic: str = env("KAFKA_VALIDATED_INPUT_TOPIC", "protein.validated-input.v1")
    prediction_topic: str = env("KAFKA_PREDICTION_TOPIC", "protein.prediction-result.v1")
    dead_letter_topic: str = env("KAFKA_DEAD_LETTER_TOPIC", "protein.dead-letter.v1")


@dataclass(frozen=True)
class RabbitMQConfig:
    url: str = env("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")
    exchange: str = env("RABBITMQ_EXCHANGE", "protein.control")
    retry_queue: str = env("RABBITMQ_RETRY_QUEUE", "protein.retry")
    notification_queue: str = env("RABBITMQ_NOTIFICATION_QUEUE", "protein.notification")


@dataclass(frozen=True)
class CassandraConfig:
    hosts: str = env("CASSANDRA_HOSTS", "localhost")
    port: int = env_int("CASSANDRA_PORT", 9042)
    keyspace: str = env("CASSANDRA_KEYSPACE", "protein_rt")

    @property
    def host_list(self) -> list[str]:
        return [host.strip() for host in self.hosts.split(",") if host.strip()]


@dataclass(frozen=True)
class ModalConfig:
    predict_url: str = env("CAFA6_PREDICT_URL", "")
    health_url: str = env("CAFA6_HEALTH_URL", "")
    timeout_seconds: int = env_int("CAFA6_TIMEOUT_SECONDS", 900)
    top_k: int = env_int("CAFA6_TOP_K", 50)

