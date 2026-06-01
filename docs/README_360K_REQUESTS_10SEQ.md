# README chay 360K request, 10 sequence/request

Tai lieu nay huong dan chay benchmark submit API voi:
- `360000` HTTP requests
- moi request gom `10` sequence records (`records` payload)
- tong cong `3,600,000` sequence records

## 1) Dieu kien truoc khi chay

1. Serving API dang chay, vi du:
```powershell
docker compose up -d --build
```

2. Co tai khoan de login API (`username`, `password`).

3. Co Python de chay script:
```powershell
python --version
```

4. Cai dependency (bao gom `tqdm`):
```powershell
pip install -r requirements.txt
```

## 2) Dry-run (kiem tra ke hoach, khong goi API)

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences_1k `
  --create-samples 1000 `
  --records-per-request 10 `
  --total-requests 360000 `
  --workers 64 `
  --max-inflight 256 `
  --checkpoint-every 20000 `
  --no-result-log `
  --dry-run
```

Ban se thay cac dong nhu:
- `Records per request: 10`
- `Planned requests: 360000`
- `Planned sequences: 3600000`

## 3) Chay benchmark that

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences_1k `
  --records-per-request 10 `
  --total-requests 360000 `
  --workers 64 `
  --max-inflight 256 `
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

## 4) Giai thich output

- `throughput_rps`: so request/giay.
- `throughput_seq_per_sec`: so sequence/giay.
- `failure_rate`: ti le request loi.
- `checkpoint_360k_x10.jsonl`: moc progress theo thoi gian.
- `summary_360k_x10.json`: ket qua tong hop cuoi run.

## 5) Neu bi timeout hoac loi nhieu

Thu theo thu tu:
1. Giam `--workers` (vi du tu `64` xuong `32`).
2. Giam `--max-inflight` (vi du tu `256` xuong `128`).
3. Tang `--timeout` (vi du `180`).
