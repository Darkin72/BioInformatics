from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


VALID_AA_RE = re.compile(r"^[ACDEFGHIKLMNPQRSTVWYBXZUOJ]+$")


def utc_now() -> datetime:
    return datetime.now(UTC)


def sequence_checksum(sequence: str) -> str:
    return hashlib.sha256(sequence.encode("utf-8")).hexdigest()


def shard_for_request(request_id: str, shard_count: int = 32) -> int:
    return int(hashlib.sha256(request_id.encode("utf-8")).hexdigest(), 16) % shard_count


class RawProteinInputEvent(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    protein_id: str
    sequence: str
    source: str = "api"
    event_time: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    checksum: str | None = None

    @field_validator("protein_id")
    @classmethod
    def protein_id_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("protein_id must not be blank")
        return value

    @field_validator("sequence")
    @classmethod
    def normalize_sequence(cls, value: str) -> str:
        sequence = re.sub(r"\s+", "", value).upper()
        if not sequence:
            raise ValueError("sequence must not be blank")
        if len(sequence) > 20000:
            raise ValueError("sequence length exceeds 20000 amino acids")
        if not VALID_AA_RE.match(sequence):
            raise ValueError("sequence contains invalid amino-acid characters")
        return sequence

    def model_post_init(self, __context: Any) -> None:
        if self.checksum is None:
            self.checksum = sequence_checksum(self.sequence)


class PredictionRow(BaseModel):
    model: str = "ensemble"
    protein_id: str
    go_term: str
    score: float
    aspect: str | None = None
    name: str | None = None


class PredictionResultEvent(BaseModel):
    request_id: str
    protein_id: str
    predicted_at: datetime = Field(default_factory=utc_now)
    model_version: str = "cafa6_modal_ensemble"
    feature_version: str = "sequence_v1"
    predicted_terms: list[str]
    score_map: dict[str, float]
    predictions: list[PredictionRow]
    threshold_used: float | None = None
    latency_ms: int | None = None
    confidence_summary: str | None = None


class DeadLetterEvent(BaseModel):
    request_id: str
    protein_id: str | None = None
    failed_at: datetime = Field(default_factory=utc_now)
    stage_name: str
    error_code: str
    error_message: str
    retryable: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)

