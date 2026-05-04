# CAFA-6 Modal Streaming Endpoint

Tài liệu này mô tả app Modal mới trong `cafa6_modal_streaming/`. App này tách riêng khỏi `cafa6_modal/` để giữ endpoint JSON cũ ổn định, đồng thời bổ sung SSE batch streaming cho request nhiều protein sequence.

## Tổng quan

App mới:

```text
cafa6_modal_streaming/
  modal_app.py
  predictor.py
  models.py
  scripts/deploy.sh
  scripts/call_streaming_endpoint.py
  .env.example
```

Modal app name:

```text
cafa6-ensemble-streaming-endpoint
```

App dùng cùng Modal volumes với endpoint cũ:

```text
cafa6-artifacts
cafa6-hf-cache
```

Đường dẫn artifact trong container vẫn là:

```text
/models/cafa6_high_performance_artifacts
```

Vì vậy không cần upload artifact mới nếu volume cũ đã có:

```text
config.json
go_terms.json
go_metadata.json
branch_checkpoints/
cafa6_high_performance_models.pt
```

Streaming predictor cũng hỗ trợ checkpoint graph-aware nếu sau này dùng:

```text
graph_aware_models.pt
```

## Deploy

```bash
bash cafa6_modal_streaming/scripts/deploy.sh
```

Modal sẽ in ra 3 URL:

```text
cafa6-stream-health
cafa6-stream-predict
cafa6-stream-predict-sse
```

Tạo `.env`:

```bash
cp cafa6_modal_streaming/.env.example cafa6_modal_streaming/.env
```

Điền URL thật:

```env
CAFA6_STREAM_HEALTH_URL=https://your-workspace--cafa6-stream-health.modal.run
CAFA6_STREAM_PREDICT_URL=https://your-workspace--cafa6-stream-predict.modal.run
CAFA6_STREAM_PREDICT_SSE_URL=https://your-workspace--cafa6-stream-predict-sse.modal.run
```

## API

### `GET cafa6-stream-health`

Health check.

Response:

```json
{
  "status": "ok",
  "device": "cuda",
  "artifact_dir": "/models/cafa6_high_performance_artifacts",
  "branches": ["bilstm_attention", "esm_mlp", "protcnn"],
  "num_go_terms": 3000,
  "threshold": 0.3,
  "embedding_model_name": "facebook/esm2_t30_150M_UR50D",
  "supports_batch_streaming": true
}
```

### `POST cafa6-stream-predict`

JSON endpoint tương thích với endpoint cũ. Không streaming.

Request:

```json
{
  "records": [
    {
      "id": "protein_1",
      "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"
    }
  ],
  "top_k": 20,
  "threshold": null,
  "include_branch_predictions": false
}
```

Response:

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
    "weights": {
      "esm_mlp": 0.5,
      "protcnn": 0.25,
      "bilstm_attention": 0.25
    },
    "threshold": 0.3,
    "top_k": 20
  }
}
```

### `POST cafa6-stream-predict-sse`

SSE batch streaming endpoint.

Request:

```json
{
  "records": [
    {
      "id": "protein_1",
      "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"
    },
    {
      "id": "protein_2",
      "sequence": "GAVLILKKKGHHEAELKPLAQSHATKHKIPIKYLEFISEAIIHVLHSR"
    }
  ],
  "top_k": 20,
  "threshold": null,
  "stream_batch_size": 2,
  "include_branch_predictions": false
}
```

Request fields:

```text
records
```

List protein inputs. Max records per request is `64`.

```text
top_k
```

Max GO terms returned per protein, after threshold filtering.

```text
threshold
```

If `null`, server uses `best_threshold_micro_f1` from `config.json`.

```text
stream_batch_size
```

Number of records inferred per streamed batch. Default is `8`; app clamps it to max `32`. Larger batches improve GPU efficiency but delay the first batch event.

```text
include_branch_predictions
```

If `true`, each batch also includes per-branch predictions for `esm_mlp`, `protcnn`, and `bilstm_attention`.

## SSE Event Format

The response content type is:

```text
text/event-stream
```

Events are sent as:

```text
event: <event_name>
data: <json>
```

### `start`

Sent immediately after the request is accepted.

```text
event: start
data: {"status":"started","total_input_records":4,"stream_batch_size":2,"top_k":20,"threshold":null,"include_branch_predictions":false}
```

### `batch`

Sent after each batch finishes inference.

```text
event: batch
data: {
  "batch_index": 0,
  "batch_start": 0,
  "batch_size": 2,
  "total_batches": 2,
  "total_records": 4,
  "predictions": [...],
  "records": [...],
  "model": {...}
}
```

The `predictions` schema is the same as the JSON endpoint:

```json
{
  "model": "ensemble",
  "protein_id": "protein_1",
  "go_term": "GO:0005525",
  "score": 0.812345,
  "aspect": "F",
  "name": "GTP binding"
}
```

### `done`

Sent after all batches complete.

```text
event: done
data: {"status":"done","elapsed_seconds":12.345}
```

### `error`

If an exception happens after streaming starts, the endpoint sends an error event.

```text
event: error
data: {"status":"error","error_type":"ValueError","message":"No non-empty input sequences were provided."}
```

Validation errors that can be detected before streaming, such as invalid `records` type or too many records, still return normal HTTP errors.

## Curl

Use `curl -N` to disable buffering:

```bash
curl -N -X POST "$CAFA6_STREAM_PREDICT_SSE_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "records": [
      {
        "id": "protein_1",
        "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"
      },
      {
        "id": "protein_2",
        "sequence": "GAVLILKKKGHHEAELKPLAQSHATKHKIPIKYLEFISEAIIHVLHSR"
      }
    ],
    "top_k": 20,
    "stream_batch_size": 1
  }'
```

## Python Client

Install:

```bash
pip install requests
```

Run the included client:

```bash
python cafa6_modal_streaming/scripts/call_streaming_endpoint.py \
  --url "$CAFA6_STREAM_PREDICT_SSE_URL" \
  --id protein_1 \
  --sequence MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV \
  --sequence GAVLILKKKGHHEAELKPLAQSHATKHKIPIKYLEFISEAIIHVLHSR \
  --top-k 20 \
  --stream-batch-size 1
```

The script prints `start`, each `batch`, and `done`.

## Browser / Frontend

Because prediction uses `POST` with JSON body, use `fetch()` streaming instead of native `EventSource`.

```js
const response = await fetch(CAFA6_STREAM_PREDICT_SSE_URL, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Accept": "text/event-stream"
  },
  body: JSON.stringify({
    records: [
      { id: "protein_1", sequence: "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV" },
      { id: "protein_2", sequence: "GAVLILKKKGHHEAELKPLAQSHATKHKIPIKYLEFISEAIIHVLHSR" }
    ],
    top_k: 20,
    stream_batch_size: 1
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });

  let boundary;
  while ((boundary = buffer.indexOf("\n\n")) >= 0) {
    const rawEvent = buffer.slice(0, boundary);
    buffer = buffer.slice(boundary + 2);

    const eventLine = rawEvent.split("\n").find((line) => line.startsWith("event:"));
    const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data:"));
    const event = eventLine?.slice("event:".length).trim() ?? "message";
    const data = JSON.parse(dataLine?.slice("data:".length).trim() ?? "{}");

    if (event === "batch") {
      console.log("batch", data.batch_index, data.predictions);
    } else if (event === "done") {
      console.log("done", data);
    } else if (event === "error") {
      console.error("stream error", data);
    }
  }
}
```

## Batch Size Tradeoff

`stream_batch_size` controls latency vs throughput.

Small batch, for example `1`:

```text
first result arrives sooner
less GPU efficient
more SSE events
```

Larger batch, for example `8` or `16`:

```text
better GPU utilization
fewer events
first result arrives later
```

For UI demos, start with `stream_batch_size=1` or `2`. For production batch jobs, use `8` or higher.

## Compatibility

The original endpoint in `cafa6_modal/` remains unchanged. Use:

```text
cafa6_modal/
```

for the old JSON-only API, and:

```text
cafa6_modal_streaming/
```

for JSON plus SSE streaming APIs.
