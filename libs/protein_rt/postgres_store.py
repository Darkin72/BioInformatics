from __future__ import annotations

import os
from typing import Any


class PostgresStore:
    def __init__(self, database_url: str | None = None):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("Install psycopg to use PostgresStore") from exc

        self._psycopg = psycopg
        self._conn = psycopg.connect(
            database_url or os.getenv("DATABASE_URL", "postgresql://protein:protein@localhost:5433/protein_metadata"),
            row_factory=dict_row,
        )
        self._conn.autocommit = True

    def close(self) -> None:
        self._conn.close()

    def list_models(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT model_version, model_name, artifact_uri, status, created_at, config
                FROM model_registry
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return list(cur.fetchall())

    def upsert_model(
        self,
        model_version: str,
        model_name: str,
        artifact_uri: str | None,
        status: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO model_registry (
                    model_version, model_name, artifact_uri, status, config
                ) VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (model_version) DO UPDATE SET
                    model_name = EXCLUDED.model_name,
                    artifact_uri = EXCLUDED.artifact_uri,
                    status = EXCLUDED.status,
                    config = EXCLUDED.config
                RETURNING model_version, model_name, artifact_uri, status, created_at, config
                """,
                (
                    model_version,
                    model_name,
                    artifact_uri,
                    status,
                    self._psycopg.types.json.Jsonb(config),
                ),
            )
            return dict(cur.fetchone())

    def list_replay_campaigns(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT replay_id, dataset_id, rate_per_second, status, created_at,
                       started_at, finished_at, config
                FROM replay_campaigns
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return list(cur.fetchall())

    def upsert_replay_campaign(
        self,
        replay_id: str,
        dataset_id: str | None,
        rate_per_second: int,
        status: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO replay_campaigns (
                    replay_id, dataset_id, rate_per_second, status, config
                ) VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (replay_id) DO UPDATE SET
                    dataset_id = EXCLUDED.dataset_id,
                    rate_per_second = EXCLUDED.rate_per_second,
                    status = EXCLUDED.status,
                    config = EXCLUDED.config
                RETURNING replay_id, dataset_id, rate_per_second, status, created_at,
                          started_at, finished_at, config
                """,
                (
                    replay_id,
                    dataset_id,
                    rate_per_second,
                    status,
                    self._psycopg.types.json.Jsonb(config),
                ),
            )
            return dict(cur.fetchone())

    def audit(
        self,
        actor: str,
        action: str,
        target_type: str,
        target_id: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO operator_audit_log (
                    actor, action, target_type, target_id, detail
                ) VALUES (%s, %s, %s, %s, %s::jsonb)
                """,
                (
                    actor,
                    action,
                    target_type,
                    target_id,
                    self._psycopg.types.json.Jsonb(detail or {}),
                ),
            )
