from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .config import CassandraConfig
from .events import DeadLetterEvent, PredictionResultEvent, RawProteinInputEvent, shard_for_request


class CassandraStore:
    def __init__(self, config: CassandraConfig):
        try:
            from cassandra.cluster import Cluster
        except ImportError as exc:
            raise RuntimeError("Install cassandra-driver to use CassandraStore") from exc

        self._cluster = Cluster(config.host_list, port=config.port)
        self._session = self._cluster.connect(config.keyspace)

    def close(self) -> None:
        self._cluster.shutdown()

    def put_raw_event(self, event: RawProteinInputEvent) -> None:
        self._session.execute(
            """
            INSERT INTO raw_protein_events (
                ingest_date, shard_id, event_ts, request_id, protein_id, source_type,
                sequence_raw, source_payload, checksum, producer_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event.event_time.date(),
                shard_for_request(event.request_id),
                event.event_time,
                event.request_id,
                event.protein_id,
                event.source,
                event.sequence,
                event.model_dump_json(),
                event.checksum,
                event.metadata.get("producer_id", "ingestion_api"),
            ),
        )

    def put_request_status(
        self,
        request_id: str,
        protein_id: str,
        status: str,
        stage_name: str,
        error_code: str | None = None,
        error_message: str | None = None,
        model_version: str | None = None,
        feature_version: str | None = None,
        retry_count: int = 0,
    ) -> None:
        now = datetime.utcnow()
        self._session.execute(
            """
            INSERT INTO request_status_by_id (
                request_id, protein_id, created_at, updated_at, current_status, error_code,
                error_message, stage_name, retry_count, model_version, feature_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                request_id,
                protein_id,
                now,
                now,
                status,
                error_code,
                error_message,
                stage_name,
                retry_count,
                model_version,
                feature_version,
            ),
        )

    def put_prediction(self, result: PredictionResultEvent) -> None:
        top_terms = result.predicted_terms
        top_scores = [float(result.score_map[term]) for term in top_terms]
        predictions_json = [row.model_dump_json() for row in result.predictions]
        self._session.execute(
            """
            INSERT INTO latest_prediction_by_protein (
                protein_id, request_id, predicted_at, model_version, top_terms, top_scores,
                prediction_rows, confidence_summary, explanation_ref, embedding_ref
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                result.protein_id,
                result.request_id,
                result.predicted_at,
                result.model_version,
                top_terms,
                top_scores,
                predictions_json,
                result.confidence_summary,
                None,
                None,
            ),
        )
        self._session.execute(
            """
            INSERT INTO prediction_history_by_protein (
                protein_id, predicted_at, request_id, model_version, feature_version,
                predicted_terms, score_map, prediction_rows, threshold_used, latency_ms
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                result.protein_id,
                result.predicted_at,
                result.request_id,
                result.model_version,
                result.feature_version,
                top_terms,
                result.score_map,
                predictions_json,
                result.threshold_used,
                result.latency_ms,
            ),
        )
        self._session.execute(
            """
            INSERT INTO prediction_by_request (
                request_id, protein_id, predicted_at, model_version, feature_version,
                predicted_terms, score_map, prediction_rows, threshold_used, latency_ms
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                result.request_id,
                result.protein_id,
                result.predicted_at,
                result.model_version,
                result.feature_version,
                top_terms,
                result.score_map,
                predictions_json,
                result.threshold_used,
                result.latency_ms,
            ),
        )
        self.put_request_status(
            request_id=result.request_id,
            protein_id=result.protein_id,
            status="SUCCEEDED",
            stage_name="prediction_persisted",
            model_version=result.model_version,
            feature_version=result.feature_version,
        )

    def put_failed_request(self, failure: DeadLetterEvent) -> None:
        self._session.execute(
            """
            INSERT INTO failed_requests_by_time (
                failure_date, status_code, failed_at, request_id, protein_id,
                stage_name, reason, retryable
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                failure.failed_at.date(),
                failure.error_code,
                failure.failed_at,
                failure.request_id,
                failure.protein_id,
                failure.stage_name,
                failure.error_message,
                failure.retryable,
            ),
        )

    def get_request_status(self, request_id: str) -> dict[str, Any] | None:
        row = self._session.execute(
            "SELECT * FROM request_status_by_id WHERE request_id = %s",
            (request_id,),
        ).one()
        return row._asdict() if row else None

    def get_latest_prediction(self, protein_id: str) -> dict[str, Any] | None:
        row = self._session.execute(
            "SELECT * FROM latest_prediction_by_protein WHERE protein_id = %s",
            (protein_id,),
        ).one()
        return row._asdict() if row else None

    def get_prediction_history(self, protein_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._session.execute(
            "SELECT * FROM prediction_history_by_protein WHERE protein_id = %s LIMIT %s",
            (protein_id, limit),
        )
        return [row._asdict() for row in rows]

    def get_prediction_by_request(self, request_id: str) -> dict[str, Any] | None:
        row = self._session.execute(
            "SELECT * FROM prediction_by_request WHERE request_id = %s",
            (request_id,),
        ).one()
        return row._asdict() if row else None
