# Benchmark Guideline (Big Data)

Tai lieu nay huong dan benchmark theo huong thuc nghiem du lieu lon (den 100M requests),
de output co the hien ro tinh chat he thong khi tai tang cao.

## 1) Chon dung loai benchmark

| Muc tieu | Lenh chinh | Ghi chu |
|---|---|---|
| Benchmark chat luong model CAFA (F-max, weighted metrics, threshold) | `python scripts\run_cafa_pk_eval.py ...` | Do chat luong du doan offline |
| Benchmark submit API inference (throughput/latency/failure) | `python scripts\stress_submit_sequences.py ...` | Do kha nang nhan request cua Serving API |

Luu y:
- `stress_submit_sequences.py` goi `POST /api/inference-requests` tren Serving API (mac dinh `http://localhost:8001`).
- Script nay benchmark submit-path cua Serving API, khong phai full data-plane `ingestion -> Kafka -> Spark`.

## 2) Chuan bi moi truong

1. Tao file env:

```powershell
Copy-Item .env.example .env
```

2. Dien it nhat cac bien sau trong `.env`:
- `CAFA6_PREDICT_URL`
- `CAFA6_HEALTH_URL`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

=> Hỏi Em Quân

3. Start stack:

```powershell
# serving-api 8001 (gốc)
docker compose up -d --build
# ingestion-api 8001, serving-api 8002
docker compose -f infra/docker/docker-compose.yml up -d --build
```

4. Check health:

```powershell
curl http://localhost:8001/health
curl http://localhost:8002/health
```

## 3) Reset history truoc moi dot benchmark

```powershell
python scripts\clear_request_history.py `
  --api-base-url http://localhost:8002 `
  --username admin `
  --password admin123 `
  --yes
```

## 4) Chay benchmark theo cac moc tai (10K -> 100M)

### 4.1 Tao bo sample co dinh

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences_1k `
  --create-samples 1000 `
  --dry-run
```

Muc tieu la co tap base record co dinh (1000 records) de so sanh cong bang giua cac moc tai.

### 4.2 Sanity run (10K)

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences_1k `
  --total-requests 10000 `
  --workers 32 `
  --max-inflight 128 `
  --progress-every 1000 `
  --checkpoint-every 5000 `
  --summary-output .\tmp\bench\summary_10k.json `
  --checkpoint-output .\tmp\bench\checkpoint_10k.jsonl `
  --no-result-log `
  --api-base-url http://localhost:8002 `
  --username admin `
  --password admin123
```

### 4.3 Sweep theo scale lon

```powershell
$levels = 100000,1000000,10000000
foreach ($n in $levels) {
  python scripts\clear_request_history.py --yes --api-base-url http://localhost:8001 --username admin --password admin123

  python scripts\stress_submit_sequences.py `
    --input-dir .\tmp\stress_sequences_1k `
    --total-requests $n `
    --workers 64 `
    --max-inflight 256 `
    --timeout 120 `
    --progress-every 50000 `
    --checkpoint-every 100000 `
    --summary-output ".\tmp\bench\summary_$n.json" `
    --checkpoint-output ".\tmp\bench\checkpoint_$n.jsonl" `
    --no-result-log `
    --username your_user `
    --password your_password
}
```

### 4.4 Chay muc tieu 100M

```powershell
python scripts\clear_request_history.py --yes --api-base-url http://localhost:8001 --username admin --password admin123

python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences_1k `
  --total-requests 100000000 `
  --workers 128 `
  --max-inflight 512 `
  --timeout 120 `
  --progress-every 1000000 `
  --checkpoint-every 1000000 `
  --latency-sample-size 500000 `
  --summary-output .\tmp\bench\summary_100m.json `
  --checkpoint-output .\tmp\bench\checkpoint_100m.jsonl `
  --no-result-log `
  --username your_user `
  --password your_password
```

Khuyen nghi cho run 100M:
- Bat buoc dung `--no-result-log` de tranh file JSONL qua lon.
- Theo doi tai he thong bang `docker stats` trong qua trinh chay.
- Neu that bai do timeout/network, giam `--workers` hoac tang `--timeout`.

## 5) Neu can luu full raw log cho 100M

Run theo chunk thay vi 1 lan, vi full JSONL 100M se rat lon:

```powershell
$chunk = 2000000
$total = 100000000
for ($start = 0; $start -lt $total; $start += $chunk) {
  $idx = [int]($start / $chunk) + 1
  python scripts\stress_submit_sequences.py `
    --input-dir .\tmp\stress_sequences_1k `
    --total-requests $chunk `
    --workers 96 `
    --max-inflight 384 `
    --progress-every 200000 `
    --summary-output ".\tmp\bench\summary_100m_chunk_$idx.json" `
    --output ".\tmp\bench\raw_chunk_$idx.jsonl" `
    --username your_user `
    --password your_password
}
```

## 6) Output can nop cho mon Big Data

Output toi thieu nen co:
1. `summary_*.json` moi moc tai: throughput, failure_rate, p50/p95/p99 estimate.
2. `checkpoint_*.jsonl`: bien dong throughput theo thoi gian (vd moi 1M requests).
3. Bang tong hop scale (10K, 100K, 1M, 10M, 100M).
4. Anh/chup man hinh `docker stats` de chung minh tai he thong.

Tao bang tong hop CSV tu cac summary:

```powershell
Get-ChildItem .\tmp\bench\summary_*.json `
| ForEach-Object {
    $j = Get-Content $_.FullName -Raw | ConvertFrom-Json
    [PSCustomObject]@{
      requests = [int64]$j.planned_total_requests
      throughput_rps = [math]::Round([double]$j.throughput_rps, 2)
      failure_rate_pct = [math]::Round(([double]$j.failure_rate * 100.0), 4)
      p95_ms = [math]::Round([double]$j.latency_ms.p95_est, 2)
      p99_ms = [math]::Round([double]$j.latency_ms.p99_est, 2)
    }
  } `
| Sort-Object requests `
| Export-Csv .\tmp\bench\scale_table.csv -NoTypeInformation
```

## 7) Diem can nhan manh khi thuyet trinh

- Khi scale tang, throughput co the khong tang tuyen tinh theo workers.
- p95/p99 latency thuong tang nhanh hon p50 khi he thong gan nguong tai.
- failure_rate la tin hieu quan trong ve gioi han he thong (timeout, 5xx, network).
- checkpoint theo moc 1M requests giup thay do on dinh theo thoi gian, khong chi nhin ket qua cuoi.

## 8) Benchmark full pipeline (neu can)

Neu muc tieu la benchmark dung nghia data-plane:
`ingestion API (/v1/proteins) -> Kafka -> Spark -> Cassandra`,
can viet script rieng de ban vao Ingestion API va poll den khi request `COMPLETED/FAILED`.
