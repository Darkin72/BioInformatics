# CAFA-6 Modal Endpoint

Thư mục này mô tả cách phục vụ ensemble CAFA-6 đã huấn luyện dưới dạng Modal GPU endpoint.

Có hai cách sử dụng:

- Dùng demo endpoint đã deploy sẵn và gửi protein sequence tới endpoint đó.
- Tạo tài khoản Modal riêng, upload artifact và deploy endpoint riêng.

## Cấu hình endpoint

URL endpoint nằm trong `cafa6_modal/.env`. Bắt đầu từ file ví dụ:

```bash
cp cafa6_modal/.env.example cafa6_modal/.env
```

Client script tự đọc `cafa6_modal/.env`. Bạn cũng có thể override URL từ command line bằng `--health-url` và `--predict-url`.

## Dùng nhanh endpoint có sẵn

Cài dependency cho client:

```bash
pip install requests
```

Gọi endpoint đã deploy:

```bash
python cafa6_modal/scripts/call_deployed_endpoint.py
```

Gọi với một sequence tùy chỉnh:

```bash
python cafa6_modal/scripts/call_deployed_endpoint.py \
  --id protein_a \
  --sequence MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV \
  --top-k 20
```

Gọi nhiều sequence trong một request:

```bash
python cafa6_modal/scripts/call_deployed_endpoint.py \
  --id protein_a \
  --sequence MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV \
  --sequence GAVLILKKKGHHEAELKPLAQSHATKHKIPIKYLEFISEAIIHVLHSR
```

Output kỳ vọng là JSON có các field `predictions`, `records` và `model`. Các row trong `predictions` phản ánh bảng output của notebook:

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

## Cài đặt và đăng nhập Modal

Dùng các bước này nếu bạn chưa có Modal endpoint và muốn deploy endpoint riêng.

Artifact có thể tải tại:

```text
https://drive.google.com/drive/folders/1DoFUaywdEyFdZJVyRK9i5X1G6D3x5j1S?usp=sharing
```

```bash
pip install modal
modal setup
```

## Upload artifact

Endpoint cần cấu trúc này trong Modal Volume:

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

Chỉ upload các file cần cho serving từ root repo. Script bỏ qua các file embedding `.npy` lớn dùng cho training/validation vì endpoint không dùng chúng.

```bash
bash cafa6_modal/scripts/upload_artifacts.sh ./cafa6_high_performance_artifacts
```

## Phát triển local với Modal

```bash
modal serve cafa6_modal/modal_app.py
```

Hoặc deploy trực tiếp:

```bash
bash cafa6_modal/scripts/deploy.sh
```

## Deploy

```bash
bash cafa6_modal/scripts/deploy.sh
```

Modal sẽ in ra hai URL:

- `cafa6-health`: endpoint `GET` để kiểm tra health.
- `cafa6-predict`: endpoint `POST` để inference.

Copy hai URL đó vào `cafa6_modal/.env`:

```env
CAFA6_HEALTH_URL=https://your-workspace--cafa6-health.modal.run
CAFA6_PREDICT_URL=https://your-workspace--cafa6-predict.modal.run
```

Sau đó gọi endpoint:

```bash
python cafa6_modal/scripts/call_deployed_endpoint.py
```

## Gọi HTTP trực tiếp

Bạn có thể gọi predict URL trực tiếp từ backend hoặc frontend:

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

Nếu muốn dùng giá trị từ `.env` trong shell:

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

Bạn cũng có thể gửi một sequence đơn:

```json
{
  "id": "protein_1",
  "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"
}
```

## Response

Response phản ánh bảng prediction trong notebook, trả về dưới dạng JSON:

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

## Tích hợp với Serving API

Serving API của repo này đọc các biến môi trường sau:

```env
CAFA6_HEALTH_URL=https://your-workspace--cafa6-health.modal.run
CAFA6_PREDICT_URL=https://your-workspace--cafa6-predict.modal.run
CAFA6_TOP_K=20
CAFA6_TIMEOUT_SECONDS=60
```

Khi user gọi `POST /api/inference-requests`, Serving API gửi request tới `CAFA6_PREDICT_URL`, sau đó map response:

- `go_term` -> `term_id`
- `name` -> `term_name`
- `aspect` `F/P/C` -> ontology `MF/BP/CC`
- `score` -> `score`
- `model.name` -> `model_version`

Nếu `CAFA6_PREDICT_URL` chưa được cấu hình hoặc Modal endpoint lỗi, request inference sẽ có trạng thái `failed` với `error_code=ANALYSIS_API_ERROR`.

## Scaling

`modal_app.py` được cấu hình cho demo traffic:

- `gpu="T4"` để giữ chi phí thấp.
- `max_containers=4` cho phép Modal scale ngang khi có nhiều request đồng thời.
- `buffer_containers=1` giữ thêm một container warm khi endpoint đang active.
- `scaledown_window=300` giữ container idle trong một khoảng ngắn để giảm cold start.
- Mỗi request nhận tối đa 64 sequence. Với job lớn hơn, hãy chia thành nhiều request.

Tăng `max_containers` nếu cần nhiều user đồng thời hơn. Chỉ tăng `min_containers` trong demo live nếu cần endpoint luôn warm, vì GPU container warm vẫn tốn credit.

## Ghi chú chi phí

Modal là serverless. Với endpoint này, chi phí chủ yếu đến từ:

- Thời gian GPU khi container khởi động, load model, xử lý request hoặc giữ warm.
- Thời gian CPU và memory trong cùng giai đoạn active/warm.
- Lưu trữ Volume, tùy plan và mức sử dụng.

Cấu hình hiện tại dùng `scaledown_window=30`, nên sau một request Modal có thể giữ GPU container khoảng nửa phút để tránh cold start tiếp theo. Điều này cải thiện latency demo nhưng có thể tốn credit khi container idle. Giảm giá trị này nếu muốn tối thiểu chi phí, hoặc chỉ đặt `min_containers=1` trong demo live nếu cần endpoint luôn warm.

Tại ngày 29 tháng 4 năm 2026, trang pricing chính thức của Modal liệt kê gói Starter là `$0` với `$30/tháng` free compute credit, và T4 GPU ở mức `$0.000164/giây` trước khi tính CPU/memory. Hãy kiểm tra trang pricing live trước khi dựa vào các con số này: https://modal.com/pricing
