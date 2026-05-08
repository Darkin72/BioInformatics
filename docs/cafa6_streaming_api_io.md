# CAFA-6 Streaming API Input/Output

Tài liệu này tập trung vào input, output và cách gọi các API trong `cafa6_modal_streaming`.

Base URLs nằm trong:

```text
cafa6_modal_streaming/.env
```

Các biến chính:

```env
CAFA6_STREAM_HEALTH_URL=...
CAFA6_STREAM_PREDICT_URL=...
CAFA6_STREAM_PREDICT_SSE_URL=...
```

## 1. Health API

```text
GET cafa6-stream-health
```

Ví dụ:

```bash
curl "$CAFA6_STREAM_HEALTH_URL"
```

Output:

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

## 2. JSON Predict API

```text
POST cafa6-stream-predict
```

API này không stream. Nó trả JSON sau khi predict xong toàn bộ request.

### Input

Batch records:

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
  "include_branch_predictions": false
}
```

Single sequence shorthand:

```json
{
  "id": "protein_1",
  "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
  "top_k": 20
}
```

Input fields:

| Field | Type | Required | Meaning |
|---|---:|---:|---|
| `records` | array | yes, unless `sequence` is used | List of protein records. |
| `records[].id` | string | no | Protein ID. Defaults to `protein_N`. |
| `records[].sequence` | string | yes | Amino acid sequence. Whitespace is removed. |
| `sequence` | string | alternative | Single sequence shorthand. |
| `id` | string | no | ID for single sequence shorthand. |
| `top_k` | integer | no | Max GO terms per protein before threshold filtering. Default `100`. |
| `threshold` | number/null | no | If `null`, uses model config `best_threshold_micro_f1`. |
| `include_branch_predictions` | boolean | no | Include predictions from each model branch. Default `false`. |

Limits:

```text
max records per request = 64
```

### Call

```bash
curl -X POST "$CAFA6_STREAM_PREDICT_URL" \
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

### Output

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

Prediction fields:

| Field | Meaning |
|---|---|
| `model` | Model that produced the row. Usually `ensemble`. |
| `protein_id` | Input protein ID. |
| `go_term` | Predicted GO term ID. |
| `score` | Sigmoid/ensemble confidence score. |
| `aspect` | GO aspect: `F`, `P`, or `C`. |
| `name` | GO term name from ontology metadata. |

If `include_branch_predictions=true`, output includes:

```json
{
  "branch_predictions": {
    "esm_mlp": [...],
    "protcnn": [...],
    "bilstm_attention": [...]
  }
}
```

## 3. SSE Batch Streaming Predict API

```text
POST cafa6-stream-predict-sse
```

API này trả `text/event-stream`. Nó xử lý input records theo batch và gửi từng batch result ngay khi batch đó infer xong.

### Input

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
  "stream_batch_size": 1,
  "include_branch_predictions": false
}
```

Additional streaming field:

| Field | Type | Required | Meaning |
|---|---:|---:|---|
| `stream_batch_size` | integer | no | Number of records per streamed batch. Default `8`, max `32`. |

Tradeoff:

```text
stream_batch_size=1
```

First result appears fastest, but GPU throughput is lower.

```text
stream_batch_size=8 or 16
```

Better throughput, but first result appears later.

### Call With Curl

Use `-N` so curl does not buffer the stream:

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

### Call With Python Client

```bash
python cafa6_modal_streaming/scripts/call_streaming_endpoint.py \
  --url "$CAFA6_STREAM_PREDICT_SSE_URL" \
  --id protein_1 \
  --sequence MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV \
  --id protein_2 \
  --sequence GAVLILKKKGHHEAELKPLAQSHATKHKIPIKYLEFISEAIIHVLHSR \
  --top-k 20 \
  --stream-batch-size 1
```

### SSE Output

The stream sends events in this order:

```text
start
batch
batch
...
done
```

If a runtime error happens after streaming starts:

```text
error
```

### `start` Event

Raw SSE:

```text
event: start
data: {"status":"started","total_input_records":2,"stream_batch_size":1,"top_k":20,"threshold":null,"include_branch_predictions":false}
```

Parsed JSON:

```json
{
  "status": "started",
  "total_input_records": 2,
  "stream_batch_size": 1,
  "top_k": 20,
  "threshold": null,
  "include_branch_predictions": false
}
```

### `batch` Event

Raw SSE:

```text
event: batch
data: {"predictions":[...],"records":[...],"model":{...},"batch_index":0,"batch_start":0,"batch_size":1,"total_batches":2,"total_records":2}
```

Parsed JSON:

```json
{
  "batch_index": 0,
  "batch_start": 0,
  "batch_size": 1,
  "total_batches": 2,
  "total_records": 2,
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

Batch metadata:

| Field | Meaning |
|---|---|
| `batch_index` | Zero-based batch index. |
| `batch_start` | Zero-based input record offset. |
| `batch_size` | Number of records in this emitted batch. |
| `total_batches` | Total number of emitted batches. |
| `total_records` | Total normalized input records. |

### `done` Event

Raw SSE:

```text
event: done
data: {"status":"done","elapsed_seconds":12.345}
```

Parsed JSON:

```json
{
  "status": "done",
  "elapsed_seconds": 12.345
}
```

### `error` Event

Raw SSE:

```text
event: error
data: {"status":"error","error_type":"ValueError","message":"No non-empty input sequences were provided."}
```

Parsed JSON:

```json
{
  "status": "error",
  "error_type": "ValueError",
  "message": "No non-empty input sequences were provided."
}
```

## 4. Frontend Fetch Streaming

Native `EventSource` is mostly for `GET`; this API uses `POST` with JSON body, so use `fetch()` and read `response.body`.

```js
const response = await fetch(CAFA6_STREAM_PREDICT_SSE_URL, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Accept": "text/event-stream"
  },
  body: JSON.stringify({
    records: [
      {
        id: "protein_1",
        sequence: "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"
      },
      {
        id: "protein_2",
        sequence: "GAVLILKKKGHHEAELKPLAQSHATKHKIPIKYLEFISEAIIHVLHSR"
      }
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

    const lines = rawEvent.split("\n");
    const event = lines
      .find((line) => line.startsWith("event:"))
      ?.slice("event:".length)
      .trim() ?? "message";
    const data = JSON.parse(
      lines
        .find((line) => line.startsWith("data:"))
        ?.slice("data:".length)
        .trim() ?? "{}"
    );

    if (event === "batch") {
      console.log("batch", data.batch_index, data.predictions);
    }
    if (event === "done") {
      console.log("done", data.elapsed_seconds);
    }
    if (event === "error") {
      console.error(data);
    }
  }
}
```

## 5. Recommended Usage

For a UI demo:

```json
{
  "top_k": 20,
  "stream_batch_size": 1,
  "include_branch_predictions": false
}
```

For a larger batch job:

```json
{
  "top_k": 50,
  "stream_batch_size": 8,
  "include_branch_predictions": false
}
```

For debugging model branches:

```json
{
  "top_k": 20,
  "stream_batch_size": 2,
  "include_branch_predictions": true
}
```

`include_branch_predictions=true` can make each SSE event much larger.
