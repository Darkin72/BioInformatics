from __future__ import annotations

import modal


APP_NAME = "cafa6-ensemble-endpoint"
ARTIFACT_VOLUME_NAME = "cafa6-artifacts"
HF_CACHE_VOLUME_NAME = "cafa6-hf-cache"
ARTIFACT_DIR = "/models/cafa6_high_performance_artifacts"
MAX_RECORDS_PER_REQUEST = 400

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
    .add_local_python_source("cafa6_modal")
)


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
class CAFA6Service:
    @modal.enter()
    def load(self):
        from cafa6_modal.predictor import CAFA6Predictor

        self.predictor = CAFA6Predictor(artifact_dir=ARTIFACT_DIR)

    @modal.fastapi_endpoint(method="GET", label="cafa6-health")
    def health(self):
        return self.predictor.health()

    @modal.fastapi_endpoint(method="POST", label="cafa6-predict", docs=True)
    def predict(self, payload: dict):
        from fastapi import HTTPException

        records = payload.get("records")
        if records is None and "sequence" in payload:
            records = [{"id": payload.get("id", "protein_1"), "sequence": payload["sequence"]}]
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
