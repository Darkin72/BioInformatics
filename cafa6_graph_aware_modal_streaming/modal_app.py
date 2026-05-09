from __future__ import annotations

import json
import time
from typing import Any

import modal


APP_NAME = "cafa6-graph-aware-streaming-endpoint"
ARTIFACT_VOLUME_NAME = "cafa6-artifacts"
HF_CACHE_VOLUME_NAME = "cafa6-hf-cache"
ARTIFACT_DIR = "/models/cafa6_graph_aware_artifacts"
MAX_RECORDS_PER_REQUEST = 128
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
    .add_local_python_source("cafa6_graph_aware_modal_streaming")
)


def sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def parse_records(payload: dict):
    records = payload.get("records")
    if records is None and "sequence" in payload:
        records = [{"id": payload.get("id", "protein_1"), "sequence": payload["sequence"]}]
    return records


def coerce_request(payload: dict):
    records = parse_records(payload)
    model_name = str(payload.get("model", "ensemble")).strip().lower()
    top_k = int(payload.get("top_k", 100))
    threshold = payload.get("threshold")
    include_branch_predictions = bool(payload.get("include_branch_predictions", False))
    stream_batch_size = int(payload.get("stream_batch_size", DEFAULT_STREAM_BATCH_SIZE))
    stream_batch_size = max(1, min(stream_batch_size, MAX_STREAM_BATCH_SIZE))
    return model_name, records, top_k, threshold, include_branch_predictions, stream_batch_size


@app.cls(
    image=image,
    gpu="T4",
    volumes={"/models": artifact_volume, "/cache": hf_cache_volume},
    timeout=900,
    startup_timeout=900,
    max_containers=4,
    buffer_containers=1,
    scaledown_window=180,
)
class CAFA6GraphAwareStreamingService:
    @modal.enter()
    def load(self):
        from cafa6_graph_aware_modal_streaming.predictor import (
            CAFA6GraphAwareStreamingPredictor,
        )

        self.predictor = CAFA6GraphAwareStreamingPredictor(artifact_dir=ARTIFACT_DIR)

    def _predict_sse(self, payload: dict):
        from fastapi import HTTPException
        from fastapi.responses import StreamingResponse

        model_name, records, top_k, threshold, include_branch_predictions, stream_batch_size = coerce_request(
            payload
        )
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

        def event_generator():
            started_at = time.time()
            yield sse(
                "start",
                {
                    "status": "started",
                    "model": model_name,
                    "total_input_records": len(records),
                    "stream_batch_size": stream_batch_size,
                    "top_k": top_k,
                    "threshold": threshold,
                    "include_branch_predictions": include_branch_predictions,
                },
            )
            try:
                for event_name, event_payload in self.predictor.iter_predict_events(
                    records=records,
                    model_name=model_name,
                    top_k=top_k,
                    threshold=threshold,
                    include_branch_predictions=include_branch_predictions,
                    stream_batch_size=stream_batch_size,
                ):
                    yield sse(event_name, event_payload)
                yield sse(
                    "done",
                    {
                        "status": "done",
                        "model": model_name,
                        "elapsed_seconds": round(time.time() - started_at, 3),
                    },
                )
            except ValueError as exc:
                yield sse(
                    "error",
                    {
                        "status": "error",
                        "model": model_name,
                        "error_type": "ValueError",
                        "message": str(exc),
                    },
                )
            except Exception as exc:
                yield sse(
                    "error",
                    {
                        "status": "error",
                        "model": model_name,
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

    @modal.fastapi_endpoint(method="POST", label="cafa6-graph-aware-predict-sse", docs=True)
    def predict_sse(self, payload: dict):
        return self._predict_sse(payload)
