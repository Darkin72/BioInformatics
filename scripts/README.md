# Scripts van hanh

Thu muc nay chua cac script phuc vu dev, test va benchmark local.

## Stress test submit sequence

Script [stress_submit_sequences.py](stress_submit_sequences.py) dang nhap vao Serving API,
gui dong thoi request den endpoint `/api/inference-requests`, va in throughput/latency/failure.

### Cai tqdm (thanh tien do)

```powershell
pip install -r requirements.txt
```

### Cach chay nhanh

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences `
  --create-samples 20 `
  --workers 8 `
  --username admin `
  --password admin123
```

### Dry-run (khong goi API)

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences `
  --repeat 10 `
  --dry-run
```

### Chay quy mo lon (khuyen nghi cho Big Data)

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences `
  --create-samples 1000 `
  --total-requests 1000 `
  --workers 32 `
  --max-inflight 256 `
  --progress-every 50000 `
  --checkpoint-every 100000 `
  --summary-output .\tmp\bench\summary_1m.json `
  --checkpoint-output .\tmp\bench\checkpoint_1m.jsonl `
  --no-result-log `
  # --api-base-url http://localhost:8001 `
  --username admin `
  --password admin123
```

### Chay dung bai toan 360K request, moi request 10 sequence

Tong sequence duoc gui: `360000 * 10 = 3600000`.

1) Kiem tra plan truoc (khong goi API):

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

2) Chay that:

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

## Tham so quan trong

- `--total-requests`: tong so request can gui. Neu dat tham so nay thi `--repeat` bi bo qua.
- `--records-per-request`: so sequence records trong moi HTTP request (`records` payload).
- `--workers`: so luong thread submit song song.
- `--max-inflight`: gioi han futures dang cho, giup khong no RAM khi so request rat lon.
- `--wait-timeout`: tan suat kiem tra trang thai `inflight` (giay), giup phat hien run dang bi treo som hon.
- `--stall-report-seconds`: neu khong co request nao hoan thanh trong N giay, script in heartbeat `[heartbeat]` (0 de tat).
- `--no-result-log`: tat ghi tung request vao JSONL (rat can cho run 10M-100M).
- `--summary-output`: ghi tong ket cuoi ky.
- `--checkpoint-every`: in progress theo moc lon (vd 1,000,000 request).
- `--checkpoint-output`: ghi cac moc progress ra JSONL de ve bieu do.
- `--latency-sample-size`: kich thuoc reservoir de uoc luong p50/p95/p99 trong run lon.
- `--no-tqdm`: tat thanh tien do `tqdm` neu can.

## Bien moi truong

- `API_BASE_URL`: mac dinh `http://localhost:8001`.

## Reset du lieu request trong moi truong dev

```powershell
python scripts\clear_request_history.py --yes
```

## Run

# ingestion-api 8001, serving-api 8002
docker compose -f infra/docker/docker-compose.yml up -d --build


python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences `
  --api-base-url http://localhost:8002 `
  --records-per-request 400 `
  --total-requests 900 `
  --workers 32 `
  --max-inflight 256 `
  --username admin`
  --password admin123


python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences `
  --api-base-url http://localhost:8002 `
  --records-per-request 400 `
  --total-requests 1 `
  --workers 32 `
  --max-inflight 256 `
  --username admin`
  --password admin123
