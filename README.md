# BioInformatics

Monorepo cho he thong du doan chuc nang protein theo thoi gian thuc.

## Muc tieu

Du an duoc to chuc quanh cac thanh phan chinh:

- `apps/ingestion_api`: nhan request hoac replay event dau vao.
- `apps/serving_api`: tra cuu trang thai, ket qua du doan, JWT auth va admin SSE.
- `jobs/spark_streaming`: pipeline Spark Structured Streaming.
- `ml/inference`: module tien xu ly, tao dac trung, suy luan, hau xu ly.
- `contracts/schemas`: JSON schema cho event contract.
- `infra`: Docker Compose, CQL schema, bootstrap ha tang.
- `docs`: tai lieu kien truc va ke hoach.
- `scripts`: script ho tro local/dev.
- `tests`: noi dat test sau nay.

## Cau truc thu muc

```text
.
|-- apps/
|   |-- ingestion_api/
|   `-- serving_api/
|-- jobs/
|   `-- spark_streaming/
|-- ml/
|   `-- inference/
|-- contracts/
|   `-- schemas/
|-- infra/
|   |-- cassandra/
|   `-- docker/
|-- docs/
|-- scripts/
`-- tests/
```

## Production v1

Luong hien tai ghep endpoint Modal CAFA-6 vao streaming stack:

```text
POST /v1/proteins
  -> apps/ingestion_api
  -> Cassandra raw_protein_events + request_status_by_id
  -> Kafka protein.raw-input.v1
  -> jobs/spark_streaming
  -> Modal CAFA6 predict endpoint
  -> Cassandra latest/history/status + Kafka protein.prediction-result.v1
  -> apps/serving_api
```

RabbitMQ nam o control-plane: ingestion publish `request.accepted` de sau nay gan retry, notification, reprocess command hoac workflow orchestration ma khong lam nghen data-plane Kafka.

### Vai tro cong nghe

- Kafka: backbone stream toc do cao cho raw input, prediction result va dead-letter event.
- RabbitMQ: control-plane cho retry, delayed job, notification, command/reprocess.
- Spark Structured Streaming: micro-batch validation, goi Modal inference, hau xu ly va ghi serving store.
- Cassandra: kho write-heavy cho raw audit, status, latest prediction, history, failure va metrics.
- Modal: GPU model-serving cho ensemble CAFA-6; backend gui `{records, top_k, threshold}` va nhan bang `predictions`.

### Chay bang Docker Compose

Huong dan day du nam o [docs/runbook.md](docs/runbook.md). Backend chay trong Docker, tru CAFA-6 Modal endpoint duoc cau hinh qua `cafa6_modal/.env`.

```bash
cp cafa6_modal/.env.example cafa6_modal/.env
docker compose -f infra/docker/docker-compose.yml up -d --build
```

Dien Modal URL vao `cafa6_modal/.env` truoc khi start stack:

```env
CAFA6_HEALTH_URL=https://your-workspace--cafa6-health.modal.run
CAFA6_PREDICT_URL=https://your-workspace--cafa6-predict.modal.run
```

API chay trong container:

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
```

Gui mot request:

```bash
curl -X POST http://localhost:8001/v1/proteins \
  -H "Content-Type: application/json" \
  -d '{"protein_id":"protein_a","sequence":"MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"}'
```

Tra cuu ket qua:

```bash
curl http://localhost:8002/v1/requests/<request_id>
curl http://localhost:8002/v1/proteins/protein_a/latest
curl http://localhost:8002/v1/proteins/protein_a/history
```

## Cau hinh Serving API

| Bien | Mac dinh | Y nghia |
| --- | --- | --- |
| `JWT_SECRET` | `dev-only-change-me` | Khoa ky JWT, can doi khi chay moi truong that |
| `JWT_EXPIRES_SECONDS` | `3600` | Thoi gian song cua access token |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5174,http://127.0.0.1:5174` | Origin frontend duoc phep goi API |
| `HOST` | `0.0.0.0` | Host khi chay qua `python apps/serving_api/src/main.py` |
| `PORT` | `8000` | Port khi chay qua entrypoint Python |
| `RELOAD` | `false` | Bat/tat reload khi chay qua entrypoint Python |
| `DATABASE_URL` | `postgresql://protein:protein@postgres:5432/protein_metadata` | Chuoi ket noi PostgreSQL metadata/quan tri |
| `CAFA6_PREDICT_URL` | rong | URL endpoint `cafa6-predict`, bat buoc de goi inference that |
| `CAFA6_HEALTH_URL` | rong | URL endpoint `cafa6-health` de kiem tra Modal service |
| `CAFA6_TOP_K` | `20` | So GO term toi da lay tu endpoint |
| `CAFA6_TIMEOUT_SECONDS` | `60` | Timeout khi goi endpoint CAFA-6 |
| `API_BASE_URL` | `http://localhost:8001` | URL Serving API dung cho script stress test |

## Tai khoan va API chinh

- Account tao moi qua giao dien dang ky co role `user`.
- Account admin duoc cau hinh qua `.env` bang `ADMIN_USERNAME` va `ADMIN_PASSWORD`.

| Phuong thuc | Endpoint | Xac thuc | Mo ta |
| --- | --- | --- | --- |
| `GET` | `/health` | Khong | Kiem tra service |
| `POST` | `/api/auth/login` | Khong | Dang nhap va nhan bearer token |
| `GET` | `/api/auth/me` | Bearer token | Lay thong tin user hien tai |
| `POST` | `/api/auth/logout` | Bearer token | Revoke token trong phien chay API |
| `GET` | `/api/admin/users/events` | token query, admin | SSE danh sach user admin |
| `GET` | `/api/metrics/pipeline/summary` | `user` hoac `admin` | Dashboard summary |
| `POST` | `/api/inference-requests` | `user` hoac `admin` | Tao request inference moi |
| `GET` | `/api/inference-requests/{request_id}` | `user` hoac `admin` | Tra cuu trang thai request |
| `GET` | `/api/proteins/{protein_id}/requests` | `user` hoac `admin` | Lay request theo protein |

Vi du dang nhap:

```powershell
$body = @{ username = "admin"; password = "admin123" } | ConvertTo-Json
$login = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8001/api/auth/login `
  -ContentType "application/json" `
  -Body $body

$token = $login.access_token
Invoke-RestMethod `
  -Headers @{ Authorization = "Bearer $token" } `
  http://localhost:8001/api/metrics/pipeline/summary
```

## Chay Frontend

Tu thu muc `frontend`:

```powershell
$env:VITE_API_BASE_URL = "http://localhost:8001"
npm run dev
```

Neu khong cau hinh `VITE_API_BASE_URL`, frontend mac dinh goi `http://localhost:8001`.

## Stress test gui nhieu file

Script [scripts/stress_submit_sequences.py](scripts/stress_submit_sequences.py) dung de gia lap nhieu file sequence duoc gui dong thoi vao Serving API that.

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences `
  --create-samples 20 `
  --workers 8 `
  --username your_user `
  --password your_password
```

## Event contract

- [contracts/schemas/raw_input_event.json](contracts/schemas/raw_input_event.json): event dau vao gom `request_id`, `protein_id`, `sequence`, `source`, `event_time`, `metadata`.
- [contracts/schemas/prediction_result_event.json](contracts/schemas/prediction_result_event.json): event ket qua gom `request_id`, `protein_id`, `predicted_at`, `model_version`, `predicted_terms`, `confidence_summary`.

Producer/consumer nen validate payload theo schema truoc khi ghi hoac doc tu streaming backbone.

## Cassandra schema

Schema ban dau nam o [infra/cassandra/schema.cql](infra/cassandra/schema.cql):

- `protein_rt.request_status_by_id`: tra cuu trang thai request theo `request_id`.
- `protein_rt.latest_prediction_by_protein`: lay ket qua du doan moi nhat theo `protein_id`.

## Docker Compose

Compose chinh cho stack v1 nam o [infra/docker/docker-compose.yml](infra/docker/docker-compose.yml). Cac URL chinh:

| Service | URL |
| --- | --- |
| Frontend | `http://localhost:5174` |
| Serving API | `http://localhost:8001` |
| Ingestion API | `http://localhost:8002` |
| Notification Service | `http://localhost:8004` |
| RabbitMQ Management | `http://localhost:15673` |
| PostgreSQL | `localhost:5433` |
| Kafka bootstrap tu host | `localhost:9093` |
| Cassandra CQL tu host | `localhost:9043` |

## Kiem tra va build

Backend:

```powershell
pytest
```

Frontend:

```powershell
cd frontend
npm run lint
npm run build
```

## Giay phep

Xem [LICENSE](LICENSE).
