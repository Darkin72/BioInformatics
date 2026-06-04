# Chạy 360K request, 10 sequence/request

Tài liệu này hướng dẫn chạy benchmark submit API với:

- `360000` HTTP request.
- Mỗi request gồm `10` sequence record trong payload `records`.
- Tổng cộng `3,600,000` sequence record.

## Điều kiện trước khi chạy

1. Serving API đang chạy. Với Kubernetes local, mở port-forward:

```powershell
kubectl -n bioinformatics port-forward svc/serving-api 8001:8000
```

2. Có tài khoản để login API (`username`, `password`).

3. Có Python để chạy script:

```powershell
python --version
```

4. Cài dependency, bao gồm `tqdm`:

```powershell
pip install -r requirements.txt
```

## Dry-run, kiểm tra kế hoạch và không gọi API

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

Bạn sẽ thấy các dòng như:

- `Records per request: 10`
- `Planned requests: 360000`
- `Planned sequences: 3600000`

## Chạy benchmark thật

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

## Giải thích output

- `throughput_rps`: số request submit/giây.
- `throughput_seq_per_sec`: số sequence/giây.
- `failure_rate`: tỉ lệ request lỗi.
- `checkpoint_360k_x10.jsonl`: mốc progress theo thời gian.
- `summary_360k_x10.json`: kết quả tổng hợp cuối run.

## Nếu bị timeout hoặc lỗi nhiều

Thử theo thứ tự:

1. Giảm `--concurrency`, ví dụ từ `64` xuống `32`.
2. Tăng `--timeout`, ví dụ `180`.
3. Giảm `--records-per-request` nếu mỗi request đang gửi quá nhiều sequence.
