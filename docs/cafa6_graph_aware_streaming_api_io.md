# Graph-Aware Streaming API I/O

Tài liệu này tập trung vào input, output và cách gọi các API trong `cafa6_graph_aware_modal_streaming`.

## Endpoint

Một endpoint duy nhất:

| Label | Env |
| --- | --- |
| `cafa6-graph-aware-predict-sse` | `CAFA6_GRAPH_AWARE_PREDICT_SSE_URL` |

`.env` mẫu nằm ở:

```text
cafa6_graph_aware_modal_streaming/.env.example
```

## Request schema

```json
{
  "records": [
    {
      "id": "protein_1",
      "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"
    }
  ],
  "model": "bilstm",
  "top_k": 20,
  "threshold": null,
  "include_branch_predictions": false,
  "stream_batch_size": 2
}
```

Notes:

- `sequence` shortcut được hỗ trợ cho 1 protein duy nhất.
- `include_branch_predictions` chỉ hữu ích với `ensemble`.
- `stream_batch_size` chỉ được dùng ở SSE.

## SSE events

`start`

```json
{
  "status": "started",
  "model": "ensemble",
  "total_input_records": 10,
  "stream_batch_size": 2,
  "top_k": 20,
  "threshold": null,
  "include_branch_predictions": true
}
```

`progress`

```json
{
  "batch_index": 0,
  "batch_start": 0,
  "batch_size": 2,
  "total_batches": 5,
  "total_records": 10,
  "model": "ensemble",
  "step": "run_protcnn",
  "status": "done"
}
```

`batch`

```json
{
  "predictions": [],
  "records": [],
  "model": {
    "name": "ensemble",
    "branches": ["bilstm", "esm_mlp", "protcnn"],
    "weights": {
      "esm_mlp": 0.5,
      "protcnn": 0.25,
      "bilstm": 0.25
    },
    "threshold": 0.4,
    "top_k": 20
  },
  "batch_index": 0,
  "batch_start": 0,
  "batch_size": 2,
  "total_batches": 5,
  "total_records": 10
}
```

`done`

```json
{
  "status": "done",
  "model": "ensemble",
  "elapsed_seconds": 4.221
}
```

`error`

```json
{
  "status": "error",
  "model": "ensemble",
  "error_type": "ValueError",
  "message": "No non-empty input sequences were provided."
}
```

## Curl examples

Ví dụ 1:

```bash
curl -N -X POST "$CAFA6_GRAPH_AWARE_PREDICT_SSE_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "records": [
      {
        "id": "protein_1",
        "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"
      }
    ],
    "model": "esm_mlp",
    "top_k": 20
  }'
```

Ví dụ 2:

```bash
curl -N -X POST "$CAFA6_GRAPH_AWARE_PREDICT_SSE_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "records": [
      {
        "id": "protein_1",
        "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"
      }
    ],
    "model": "protcnn",
    "top_k": 20,
    "stream_batch_size": 1
  }'
```

## Cách chọn model

- Đặt `model="ensemble"` khi muốn output cuối dùng weighted average từ `config.json`.
- Đặt `model="esm_mlp"`, `model="protcnn"`, `model="bilstm"` khi muốn inspect từng branch riêng.
- Nếu artifact bị thiếu branch tương ứng, endpoint trả `400`.

## Progress step semantics

- `normalize_input`: request đã được validate và chuẩn hóa sequence.
- `batch_started`: bắt đầu xử lý một batch stream.
- `extract_esm_embeddings`: đang hoặc đã sinh embedding cho nhánh ESM.
- `run_esm_mlp`: đang hoặc đã chạy head `esm_mlp`.
- `encode_sequence_tensor`: đang hoặc đã encode sequence thành tensor chỉ số amino acid.
- `run_protcnn`: đang hoặc đã chạy nhánh `protcnn`.
- `run_bilstm`: đang hoặc đã chạy nhánh `bilstm`.
- `select_model_output`: áp dụng cho model đơn, chọn output branch cuối.
- `combine_ensemble`: áp dụng cho `ensemble`, trộn xác suất theo weight trong config.
- `postprocess_predictions`: lọc `top_k`, áp `threshold`, map GO metadata, đóng gói response batch.
