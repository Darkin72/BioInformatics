# CAFA-6 Graph-Aware Modal Streaming

Tài liệu này mô tả app Modal mới trong `cafa6_graph_aware_modal_streaming/`. App dùng artifact từ `cafa6_graph_aware_artifacts/` và chỉ giữ một SSE endpoint để tránh vượt limit web endpoint của Modal workspace. Model thực thi được chọn bằng trường `model` trong request body: `ensemble`, `esm_mlp`, `protcnn`, `bilstm`.

## Thư mục

```text
cafa6_graph_aware_modal_streaming/
  .env.example
  README.md
  modal_app.py
  models.py
  predictor.py
  scripts/
    call_streaming_endpoint.py
    deploy.sh
    upload_artifacts.sh
```

## Artifact được mount trong Modal Volume

App đọc từ:

```text
/models/cafa6_graph_aware_artifacts
```

Cấu trúc tối thiểu:

```text
cafa6_graph_aware_artifacts/
  config.json
  go_terms.json
  go_metadata.json
  branch_checkpoints/
    esm_mlp.pt
    protcnn.pt
    bilstm_attention.pt
  graph_aware_models.pt
```

`predictor.py` ưu tiên load từ `branch_checkpoints/*.pt`. Nếu thiếu branch checkpoint, nó fallback sang `graph_aware_models.pt`.

## Upload artifact lên Modal Volume

```bash
bash cafa6_graph_aware_modal_streaming/scripts/upload_artifacts.sh ./cafa6_graph_aware_artifacts
```

Script sẽ put artifact vào remote path:

```text
/cafa6_graph_aware_artifacts
```

## Deploy

```bash
bash cafa6_graph_aware_modal_streaming/scripts/deploy.sh
```

App name trên Modal:

```text
cafa6-graph-aware-streaming-endpoint
```

Label được tạo:

- `cafa6-graph-aware-predict-sse`

Copy URL sau deploy vào `cafa6_graph_aware_modal_streaming/.env` từ `.env.example`.

## Input cho SSE endpoint

Request body chấp nhận một trong hai dạng:

```json
{
  "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"
}
```

hoặc:

```json
{
  "records": [
    {
      "id": "protein_1",
      "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"
    }
  ],
  "model": "ensemble",
  "top_k": 50,
  "threshold": 0.4,
  "include_branch_predictions": false,
  "stream_batch_size": 4
}
```

Ý nghĩa:

- `model`: một trong `ensemble`, `esm_mlp`, `protcnn`, `bilstm`.
- `records`: danh sách protein.
- `id`: protein id. Nếu trùng, app tự thêm suffix `_2`, `_3`, ...
- `sequence`: amino-acid sequence. Sequence rỗng bị bỏ qua.
- `top_k`: số GO term giữ lại trước khi lọc threshold.
- `threshold`: nếu null thì dùng `best_threshold_micro_f1` trong `config.json`.
- `include_branch_predictions`: chỉ có ý nghĩa cho endpoint `ensemble`.
- `stream_batch_size`: chỉ dùng cho endpoint SSE.

## Output SSE

Endpoint SSE duy nhất stream theo event:

1. `start`
2. nhiều event `progress`
3. event `batch`
4. `done`

Nếu lỗi sau khi stream đã bắt đầu thì trả event `error`.

`progress` được bắn ra khi pipeline hoàn thành từng bước nội bộ của từng batch, nên frontend/backend có thể cập nhật tiến độ chi tiết thay vì chỉ đợi đến lúc có kết quả cuối batch.

Ví dụ `start`:

```text
event: start
data: {"status":"started","model":"protcnn","total_input_records":10,"stream_batch_size":4,"top_k":20,"threshold":0.4,"include_branch_predictions":false}
```

Ví dụ `batch`:

```text
event: batch
data: {"predictions":[...],"records":[...],"model":{"name":"protcnn","resolved_branch":"protcnn","threshold":0.4,"top_k":20},"batch_index":0,"batch_start":0,"batch_size":4,"total_batches":3,"total_records":10}
```

Ví dụ `progress`:

```text
event: progress
data: {"batch_index":0,"batch_start":0,"batch_size":4,"total_batches":3,"total_records":10,"model":"ensemble","step":"extract_esm_embeddings","status":"done","embedding_rows":4,"embedding_dim":640}
```

Ví dụ `done`:

```text
event: done
data: {"status":"done","model":"protcnn","elapsed_seconds":2.731}
```

## Cách app đang làm inference

Luồng xử lý trong `predictor.py`:

1. Chuẩn hóa input record, upper-case sequence, bỏ whitespace, loại sequence rỗng.
2. Với `esm_mlp`: tokenize sequence bằng model trong `config.json`, lấy embedding bằng ESM2, pooling theo `embedding_pooling`, rồi chạy MLP.
3. Với `protcnn` và `bilstm`: encode sequence sang tensor chỉ số amino acid với `sequence_max_length`, rồi chạy branch tương ứng.
4. Nếu gọi `ensemble`, app lấy xác suất của từng branch, đọc `active_ensemble_weights` hoặc `ensemble_weights` trong `config.json`, normalize weight rồi cộng có trọng số.
5. Lấy `top_k`, lọc theo `threshold`, rồi map GO term sang `aspect` và `name` từ `go_metadata.json`.
6. Với SSE, app chia `records` thành nhiều batch nhỏ để gửi incrementally.

Các `progress.step` hiện có:

- `normalize_input`
- `batch_started`
- `extract_esm_embeddings`
- `run_esm_mlp`
- `encode_sequence_tensor`
- `run_protcnn`
- `run_bilstm`
- `select_model_output`
- `combine_ensemble`
- `postprocess_predictions`

Không phải request nào cũng đi qua đủ mọi step. Ví dụ:

- `model="esm_mlp"` sẽ không có `encode_sequence_tensor`, `run_protcnn`, `run_bilstm`.
- `model="protcnn"` sẽ không có `extract_esm_embeddings`.
- `model="ensemble"` sẽ có nhiều step hơn vì phải tính nhiều branch rồi combine.

## Ví dụ gọi SSE bằng script

```bash
python cafa6_graph_aware_modal_streaming/scripts/call_streaming_endpoint.py \
  --model ensemble \
  --sequence MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV \
  --top-k 20 \
  --stream-batch-size 1
```

Gọi branch riêng:

```bash
python cafa6_graph_aware_modal_streaming/scripts/call_streaming_endpoint.py \
  --model bilstm \
  --sequence MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV
```

## Lỗi validation

Trước khi stream bắt đầu, các lỗi sau trả HTTP error bình thường:

- thiếu `records` và cũng không có `sequence`
- `records` không phải list
- quá `64` records mỗi request
- model không được hỗ trợ
- toàn bộ sequence rỗng
