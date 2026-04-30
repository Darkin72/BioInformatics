from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from libs.protein_rt.cassandra_store import CassandraStore
from libs.protein_rt.config import CassandraConfig


app = FastAPI(title="Protein Realtime Serving API", version="0.1.0")


class AppState:
    cassandra: CassandraStore | None = None


state = AppState()


def serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): serialize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [serialize_value(item) for item in value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [serialize_value(item) for item in value]
    return value


def serialize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: serialize_value(value) for key, value in row.items()}


@app.on_event("startup")
def startup() -> None:
    state.cassandra = CassandraStore(CassandraConfig())


@app.on_event("shutdown")
def shutdown() -> None:
    if state.cassandra:
        state.cassandra.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/requests/{request_id}")
def get_request_status(request_id: str) -> dict[str, Any]:
    if state.cassandra is None:
        raise HTTPException(status_code=503, detail="Cassandra is not initialized")
    row = serialize_row(state.cassandra.get_request_status(request_id))
    if row is None:
        raise HTTPException(status_code=404, detail="request_id not found")
    return row


@app.get("/v1/requests/{request_id}/prediction")
def get_request_prediction(request_id: str) -> dict[str, Any]:
    if state.cassandra is None:
        raise HTTPException(status_code=503, detail="Cassandra is not initialized")
    row = serialize_row(state.cassandra.get_prediction_by_request(request_id))
    if row is None:
        raise HTTPException(status_code=404, detail="prediction for request_id not found")
    return row


@app.get("/v1/proteins/{protein_id}/latest")
def get_latest_prediction(protein_id: str) -> dict[str, Any]:
    if state.cassandra is None:
        raise HTTPException(status_code=503, detail="Cassandra is not initialized")
    row = serialize_row(state.cassandra.get_latest_prediction(protein_id))
    if row is None:
        raise HTTPException(status_code=404, detail="protein_id not found")
    return row


@app.get("/v1/proteins/{protein_id}/history")
def get_prediction_history(
    protein_id: str,
    limit: int = Query(default=20, ge=1, le=200),
) -> list[dict[str, Any]]:
    if state.cassandra is None:
        raise HTTPException(status_code=503, detail="Cassandra is not initialized")
    return [serialize_row(row) or {} for row in state.cassandra.get_prediction_history(protein_id, limit)]


def main() -> None:
    import uvicorn

    uvicorn.run("apps.serving_api.src.main:app", host="0.0.0.0", port=8002)


if __name__ == "__main__":
    main()
