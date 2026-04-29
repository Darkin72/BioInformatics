# CAFA-6 Modal Endpoint

Serve the trained CAFA-6 ensemble as a Modal GPU endpoint.

There are two ways to use this folder:

- Use the already deployed demo endpoint and send sequences to it.
- Create your own Modal account, upload artifacts, and deploy your own endpoint.

## 0. Endpoint config

Endpoint URLs live in `cafa6_modal/.env`. Start from the example file:

```bash
cp cafa6_modal/.env.example cafa6_modal/.env
```

The client script reads `cafa6_modal/.env` automatically. You can also override URLs from the command line with `--health-url` and `--predict-url`.

## Quick use existing endpoint

Install the client dependency:

```bash
pip install requests
```

Create `.env` from the checked-in example:

```bash
cp cafa6_modal/.env.example cafa6_modal/.env
```

Call the deployed endpoint:

```bash
python cafa6_modal/scripts/call_deployed_endpoint.py
```

Call with one custom sequence:

```bash
python cafa6_modal/scripts/call_deployed_endpoint.py \
  --id protein_a \
  --sequence MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV \
  --top-k 20
```

Call with multiple sequences in one request:

```bash
python cafa6_modal/scripts/call_deployed_endpoint.py \
  --id protein_a \
  --sequence MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV \
  --sequence GAVLILKKKGHHEAELKPLAQSHATKHKIPIKYLEFISEAIIHVLHSR
```

Expected output is JSON with `predictions`, `records`, and `model` fields. The `predictions` rows mirror the notebook output table:

```json
{
  "model": "ensemble",
  "protein_id": "protein_a",
  "go_term": "GO:0005515",
  "score": 0.487749,
  "aspect": "F",
  "name": "protein binding"
}
```

## 1. Install and login

Use these steps if you do not have a Modal endpoint yet and want to deploy your own.

```bash
pip install modal
modal setup
```

## 2. Upload artifacts

The endpoint expects this path inside the Modal Volume:

```text
/cafa6_high_performance_artifacts/
  config.json
  go_terms.json
  go_metadata.json
  branch_checkpoints/
    esm_mlp.pt
    protcnn.pt
    bilstm_attention.pt
  cafa6_high_performance_models.pt
```

Upload only the files needed for serving from the repo root. The script skips large
training/validation `.npy` embedding files because the endpoint does not use them.

```bash
bash cafa6_modal/scripts/upload_artifacts.sh ./cafa6_high_performance_artifacts
```

## 3. Develop locally against Modal

```bash
modal serve cafa6_modal/modal_app.py
```

or

```bash
bash cafa6_modal/scripts/deploy.sh
```

## 4. Deploy

```bash
bash cafa6_modal/scripts/deploy.sh
```

Modal prints two URLs:

- `cafa6-health`: GET health check.
- `cafa6-predict`: POST inference endpoint.

Copy the printed URLs into `cafa6_modal/.env`:

```env
CAFA6_HEALTH_URL=https://your-workspace--cafa6-health.modal.run
CAFA6_PREDICT_URL=https://your-workspace--cafa6-predict.modal.run
```

Then call your endpoint:

```bash
python cafa6_modal/scripts/call_deployed_endpoint.py
```

## 5. Direct HTTP call

You can call the predict URL directly from any backend/frontend:

```bash
curl -X POST "https://your-workspace--cafa6-predict.modal.run" \
  -H "Content-Type: application/json" \
  -d '{
    "records": [
      {
        "id": "protein_1",
        "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"
      }
    ],
    "top_k": 20,
    "threshold": null
  }'
```

If you want to use values from `.env` in your shell:

```bash
set -a
source cafa6_modal/.env
set +a
curl -X POST "$CAFA6_PREDICT_URL" \
  -H "Content-Type: application/json" \
  -d '{"sequence":"MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"}'
```

## Request

```json
{
  "records": [
    {
      "id": "protein_1",
      "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"
    }
  ],
  "top_k": 50,
  "threshold": null,
  "include_branch_predictions": false
}
```

You can also send a single sequence:

```json
{
  "id": "protein_1",
  "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"
}
```

## Response

The response mirrors the notebook prediction table, returned as JSON:

```json
{
  "predictions": [
    {
      "model": "ensemble",
      "protein_id": "protein_1",
      "go_term": "GO:0005525",
      "score": 0.812345,
      "aspect": "F",
      "name": "GTP binding"
    }
  ],
  "records": [
    {
      "protein_id": "protein_1",
      "length": 45,
      "sequence_preview": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"
    }
  ],
  "model": {
    "name": "ensemble",
    "branches": ["bilstm_attention", "esm_mlp", "protcnn"],
    "weights": { "esm_mlp": 0.5, "protcnn": 0.25, "bilstm_attention": 0.25 },
    "threshold": 0.0,
    "top_k": 50
  }
}
```

## Scaling

`modal_app.py` is configured for demo traffic:

- `gpu="T4"` keeps cost low.
- `max_containers=4` lets Modal scale horizontally under concurrent traffic.
- `buffer_containers=1` keeps one extra warm container while active.
- `scaledown_window=300` keeps idle containers alive briefly to reduce cold starts.
- Each request accepts up to 64 sequences. Send larger jobs as multiple requests.

Increase `max_containers` for more concurrent users. Increase `min_containers` only during a live demo if you need a permanently warm endpoint, because warm GPU containers cost credits.

## Cost notes

Modal is serverless. For this endpoint, cost mainly comes from:

- GPU time while a container is starting, loading models, processing requests, or staying warm.
- CPU and memory time for the same active/warm container period.
- Storage for Volumes, if applicable to your plan and usage.

The current config uses `scaledown_window=30`, so after a request Modal may keep the GPU container around for up to about half a minute to avoid another cold start. That improves demo latency but can spend credits while the container is idle. Set it lower if you want to minimize cost, or set `min_containers=1` only during a live demo if you want the endpoint always warm.

As of April 29, 2026, Modal's official pricing page lists Starter as `$0` with `$30/month` free compute credit, and T4 GPU at `$0.000164/sec` before CPU/memory charges. Check the live pricing page before relying on these numbers: https://modal.com/pricing
