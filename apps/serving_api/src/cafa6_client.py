"""Client for the real CAFA-6 Modal inference endpoint."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

VALID_AMINO_ACIDS = set("ACDEFGHIKLMNPQRSTVWY")
FEATURE_VERSION = "cafa6-modal-endpoint-v1"


class Cafa6AnalysisError(RuntimeError):
    """Raised when the CAFA-6 endpoint cannot produce a prediction."""


class Cafa6ValidationError(ValueError):
    """Raised when input is invalid before calling the CAFA-6 endpoint."""


@dataclass(frozen=True)
class Cafa6PredictionTerm:
    term_id: str
    term_name: str | None
    ontology: str | None
    score: float


@dataclass(frozen=True)
class Cafa6AnalysisResult:
    model_version: str
    feature_version: str
    top_terms: list[Cafa6PredictionTerm]
    confidence_summary: str
    latency_ms: int


def run_cafa6_analysis(protein_id: str, sequence: str) -> Cafa6AnalysisResult:
    """Call the configured CAFA-6 Modal endpoint for one protein sequence."""
    predict_url = os.getenv("CAFA6_PREDICT_URL", "").strip()
    if not predict_url:
        raise Cafa6AnalysisError("CAFA6_PREDICT_URL is not configured.")

    top_k = int(os.getenv("CAFA6_TOP_K", "20"))
    timeout_seconds = float(os.getenv("CAFA6_TIMEOUT_SECONDS", "60"))
    normalized_sequence = normalize_sequence(sequence)
    validate_sequence(normalized_sequence)

    payload = {
        "records": [
            {
                "id": protein_id,
                "sequence": normalized_sequence,
            }
        ],
        "top_k": top_k,
        "threshold": None,
        "include_branch_predictions": False,
    }

    started_at = perf_counter()
    response_payload = post_json(predict_url, payload, timeout_seconds)
    latency_ms = max(1, round((perf_counter() - started_at) * 1000))

    predictions = response_payload.get("predictions")
    if not isinstance(predictions, list):
        raise Cafa6AnalysisError("CAFA-6 endpoint response is missing predictions.")

    top_terms = [
        map_prediction_row(row)
        for row in predictions
        if isinstance(row, dict) and str(row.get("protein_id", protein_id)) == protein_id
    ]

    if not top_terms:
        top_terms = [
            map_prediction_row(row)
            for row in predictions
            if isinstance(row, dict)
        ]

    top_terms = sorted(top_terms, key=lambda term: term.score, reverse=True)[:top_k]
    model_payload = response_payload.get("model")
    model_name = "ensemble"
    if isinstance(model_payload, dict) and model_payload.get("name"):
        model_name = str(model_payload["name"])

    return Cafa6AnalysisResult(
        model_version=f"cafa6-modal-{model_name}",
        feature_version=FEATURE_VERSION,
        top_terms=top_terms,
        confidence_summary=build_confidence_summary(protein_id, normalized_sequence, top_terms),
        latency_ms=latency_ms,
    )


def post_json(url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    request = Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise Cafa6AnalysisError(
            f"CAFA-6 endpoint returned HTTP {exc.code}: {detail}"
        ) from exc
    except URLError as exc:
        raise Cafa6AnalysisError(f"Cannot reach CAFA-6 endpoint: {exc.reason}") from exc
    except TimeoutError as exc:
        raise Cafa6AnalysisError("CAFA-6 endpoint request timed out.") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise Cafa6AnalysisError("CAFA-6 endpoint returned invalid JSON.") from exc

    if not isinstance(parsed, dict):
        raise Cafa6AnalysisError("CAFA-6 endpoint returned an unexpected JSON shape.")

    return parsed


def map_prediction_row(row: dict[str, Any]) -> Cafa6PredictionTerm:
    term_id = str(row.get("go_term", "")).strip()
    if not term_id:
        raise Cafa6AnalysisError("CAFA-6 prediction row is missing go_term.")

    return Cafa6PredictionTerm(
        term_id=term_id,
        term_name=str(row["name"]) if row.get("name") is not None else None,
        ontology=map_aspect(row.get("aspect")),
        score=float(row.get("score", 0)),
    )


def map_aspect(aspect: Any) -> str | None:
    return {
        "F": "MF",
        "P": "BP",
        "C": "CC",
        "MF": "MF",
        "BP": "BP",
        "CC": "CC",
    }.get(str(aspect), None)


def normalize_sequence(sequence: str) -> str:
    return "".join(sequence.upper().split())


def validate_sequence(sequence: str) -> None:
    if not sequence:
        raise Cafa6ValidationError("Sequence is required.")

    invalid_symbols = sorted(set(sequence) - VALID_AMINO_ACIDS)
    if invalid_symbols:
        joined = ", ".join(invalid_symbols)
        raise Cafa6ValidationError(f"Sequence contains unsupported symbols: {joined}.")


def build_confidence_summary(
    protein_id: str,
    sequence: str,
    top_terms: list[Cafa6PredictionTerm],
) -> str:
    if not top_terms:
        return (
            f"CAFA-6 Modal endpoint processed {protein_id} with "
            f"{len(sequence)} amino acids but returned no GO terms."
        )

    top_term = top_terms[0]
    return (
        f"CAFA-6 Modal endpoint processed {protein_id} with {len(sequence)} amino acids; "
        f"top GO term is {top_term.term_id} with score {top_term.score:.3f}."
    )
