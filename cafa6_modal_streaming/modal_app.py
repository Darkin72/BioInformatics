from __future__ import annotations

import json
import time
from typing import Any

import modal


APP_NAME = "cafa6-ensemble-streaming-endpoint"
ARTIFACT_VOLUME_NAME = "cafa6-artifacts"
HF_CACHE_VOLUME_NAME = "cafa6-hf-cache"
ARTIFACT_DIR = "/models/cafa6_high_performance_artifacts"
MAX_RECORDS_PER_REQUEST = 64
DEFAULT_STREAM_BATCH_SIZE = 8
MAX_STREAM_BATCH_SIZE = 32

app = modal.App(APP_NAME)

artifact_volume = modal.Volume.from_name(ARTIFACT_VOLUME_NAME, create_if_missing=True)
hf_cache_volume = modal.Volume.from_name(HF_CACHE_VOLUME_NAME, create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "fastapi[standard]>=0.115.0",
        "numpy>=1.26.0",
        "torch>=2.4.0",
        "transformers>=4.44.0",
        "accelerate>=0.34.0",
        "safetensors>=0.4.4",
    )
    .env(
        {
            "HF_HOME": "/cache/huggingface",
            "TRANSFORMERS_CACHE": "/cache/huggingface/transformers",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    .add_local_python_source("cafa6_modal_streaming")
)


def sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def parse_records(payload: dict):
    records = payload.get("records")
    if records is None and "sequence" in payload:
        records = [{"id": payload.get("id", "protein_1"), "sequence": payload["sequence"]}]
    return records


@app.cls(
    image=image,
    gpu="T4",
    volumes={"/models": artifact_volume, "/cache": hf_cache_volume},
    timeout=900,
    startup_timeout=900,
    max_containers=4,
    buffer_containers=1,
    scaledown_window=30,
)
class CAFA6StreamingService:
    @modal.enter()
    def load(self):
        from cafa6_modal_streaming.predictor import CAFA6StreamingPredictor

        self.predictor = CAFA6StreamingPredictor(artifact_dir=ARTIFACT_DIR)

    @modal.fastapi_endpoint(method="GET", label="cafa6-stream-health")
    def health(self):
        return self.predictor.health()

    @modal.fastapi_endpoint(method="POST", label="cafa6-stream-predict", docs=True)
    def predict(self, payload: dict):
        from fastapi import HTTPException

        records = parse_records(payload)
        if not isinstance(records, list):
            raise HTTPException(
                status_code=400,
                detail="Request must include records: [{id, sequence}, ...].",
            )
        if len(records) > MAX_RECORDS_PER_REQUEST:
            raise HTTPException(
                status_code=413,
                detail=f"Too many records. Max records per request is {MAX_RECORDS_PER_REQUEST}.",
            )

        try:
            return self.predictor.predict(
                records=records,
                top_k=int(payload.get("top_k", 100)),
                threshold=payload.get("threshold"),
                include_branch_predictions=bool(payload.get("include_branch_predictions", False)),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @modal.fastapi_endpoint(method="POST", label="cafa6-stream-predict-sse", docs=True)
    def predict_sse(self, payload: dict):
        from fastapi import HTTPException
        from fastapi.responses import StreamingResponse

        records = parse_records(payload)
        if not isinstance(records, list):
            raise HTTPException(
                status_code=400,
                detail="Request must include records: [{id, sequence}, ...].",
            )
        if len(records) > MAX_RECORDS_PER_REQUEST:
            raise HTTPException(
                status_code=413,
                detail=f"Too many records. Max records per request is {MAX_RECORDS_PER_REQUEST}.",
            )

        top_k = int(payload.get("top_k", 100))
        threshold = payload.get("threshold")
        include_branch_predictions = bool(payload.get("include_branch_predictions", False))
        stream_batch_size = int(payload.get("stream_batch_size", DEFAULT_STREAM_BATCH_SIZE))
        stream_batch_size = max(1, min(stream_batch_size, MAX_STREAM_BATCH_SIZE))

        def event_generator():
            started_at = time.time()
            yield sse(
                "start",
                {
                    "status": "started",
                    "total_input_records": len(records),
                    "stream_batch_size": stream_batch_size,
                    "top_k": top_k,
                    "threshold": threshold,
                    "include_branch_predictions": include_branch_predictions,
                },
            )
            try:
                for batch in self.predictor.iter_predict_batches(
                    records=records,
                    top_k=top_k,
                    threshold=threshold,
                    include_branch_predictions=include_branch_predictions,
                    stream_batch_size=stream_batch_size,
                ):
                    yield sse("batch", batch)
                yield sse(
                    "done",
                    {
                        "status": "done",
                        "elapsed_seconds": round(time.time() - started_at, 3),
                    },
                )
            except ValueError as exc:
                yield sse(
                    "error",
                    {
                        "status": "error",
                        "error_type": "ValueError",
                        "message": str(exc),
                    },
                )
            except Exception as exc:
                yield sse(
                    "error",
                    {
                        "status": "error",
                        "error_type": exc.__class__.__name__,
                        "message": str(exc),
                    },
                )

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
