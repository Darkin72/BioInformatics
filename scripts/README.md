# Script vận hành

Thư mục này chứa các script phục vụ dev, test và benchmark local.

## Stress test submit sequence

Script [stress_submit_sequences.py](stress_submit_sequences.py) đăng nhập vào Serving API, gửi đồng thời request đến endpoint `/api/inference-requests`, đợi từng request về terminal status (`completed`, `failed`, `cancelled`) rồi mới gửi request tiếp theo cho slot concurrent đó. Throughput/latency vì vậy là end-to-end, không chỉ là thời gian API accept request.

## Cài dependency

```powershell
pip install -r requirements.txt
```

## Chạy nhanh

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences `
  --create-samples 20 `
  --concurrency 8 `
  --username admin `
  --password admin123
```

## Dry-run, không gọi API

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences `
  --repeat 10 `
  --dry-run
```

## Chạy quy mô lớn

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences `
  --create-samples 1000 `
  --total-requests 1000 `
  --concurrency 32 `
  --progress-every 50000 `
  --checkpoint-every 100000 `
  --summary-output .\tmp\bench\summary_1m.json `
  --checkpoint-output .\tmp\bench\checkpoint_1m.jsonl `
  --no-result-log `
  --api-base-url http://localhost:8001 `
  --username admin `
  --password admin123
```

## Bài toán 360K request, 10 sequence/request

Tổng sequence được gửi: `360000 * 10 = 3600000`.

Kiểm tra plan trước, không gọi API:

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences_1k `
  --create-samples 1000 `
  --records-per-request 10 `
  --total-requests 360000 `
  --concurrency 64 `
  --checkpoint-every 20000 `
  --no-result-log `
  --dry-run
```

Chạy thật:

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences_1k `
  --records-per-request 10 `
  --total-requests 360000 `
  --concurrency 64 `
  --timeout 120 `
  --progress-every 10000 `
  --checkpoint-every 20000 `
  --summary-output .\tmp\bench\summary_360k_x10.json `
  --checkpoint-output .\tmp\bench\checkpoint_360k_x10.jsonl `
  --no-result-log `
  --api-base-url http://localhost:8001 `
  --username your_user `
  --password your_password
```

## Tham số quan trọng

- `--total-requests`: tổng số request cần gửi. Nếu đặt tham số này thì `--repeat` bị bỏ qua.
- `--records-per-request`: số sequence record trong mỗi HTTP request (`records` payload).
- `--concurrency`: số request HTTP chạy đồng thời. Mặc định script giữ đúng N request đang bay, giống N user cùng submit.
- `--workers`: alias cũ của `--concurrency`.
- `--max-inflight`: trong chế độ đợi completed, giá trị cao hơn `--concurrency` bị bỏ qua để không gửi thêm request trước khi slot cũ xong.
- `--poll-interval`: số giây giữa mỗi lần poll `/api/inference-requests/{request_id}`.
- `--completion-timeout`: giới hạn thời gian đợi một request về terminal status; `0` là không giới hạn.
- `--no-start-gate`: tắt start gate. Mặc định bật để wave đầu tiên của N request bắt đầu gần như cùng lúc.
- `--wait-timeout`: tần suất kiểm tra trạng thái `inflight`, giúp phát hiện run bị treo sớm hơn.
- `--stall-report-seconds`: nếu không có request nào hoàn thành trong N giây, script in heartbeat `[heartbeat]`; đặt `0` để tắt.
- `--no-result-log`: tắt ghi từng request vào JSONL, rất cần cho run 10M-100M.
- `--summary-output`: ghi tổng kết cuối kỳ.
- `--checkpoint-every`: in progress theo mốc lớn, ví dụ 1,000,000 request.
- `--checkpoint-output`: ghi các mốc progress ra JSONL để vẽ biểu đồ.
- `--latency-sample-size`: kích thước reservoir để ước lượng p50/p95/p99 trong run lớn.
- `--no-tqdm`: tắt thanh tiến độ `tqdm` nếu cần.

## Biến môi trường

- `API_BASE_URL`: mặc định `http://localhost:8001`.

## Reset dữ liệu request trong môi trường dev

```powershell
python scripts\clear_request_history.py --yes
```

## Ghi chú chạy với Kubernetes local

Khi dùng stack Kubernetes, mở Serving API bằng port-forward trước:

```powershell
kubectl -n bioinformatics port-forward svc/serving-api 8001:8000
```

Sau đó chạy stress test với `--api-base-url http://localhost:8001`.
