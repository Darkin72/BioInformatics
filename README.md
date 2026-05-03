# BioInformatics Realtime Protein Function Prediction

Monorepo cho hệ thống dự đoán chức năng protein theo thời gian thực. Dự án hướng tới luồng xử lý `ingest -> Kafka -> Spark Structured Streaming -> ML inference -> Cassandra -> Serving API/Dashboard`, lấy bối cảnh từ bài toán CAFA-6 Protein Function Prediction.

## Mục tiêu

- Nhận chuỗi protein từ API, file replay hoặc nguồn stream giả lập.
- Chuẩn hóa event đầu vào bằng JSON Schema.
- Xử lý stream bằng Spark, tạo feature và gọi module inference.
- Ghi trạng thái request, kết quả dự đoán, metric và lịch sử xử lý vào Cassandra.
- Cung cấp Serving API và dashboard để theo dõi pipeline, tra cứu trạng thái request và xem latest prediction.

## Trạng thái hiện tại

Dự án hiện là skeleton có một số phần demo đã chạy được:

- `apps/serving_api`: FastAPI demo có JWT auth, RBAC, dashboard summary, tạo request inference, tra cứu request và latest prediction bằng dữ liệu in-memory.
- `frontend`: React + TypeScript + Vite dashboard, có mock API khi không cấu hình backend và có thể gọi Serving API thật qua `VITE_API_BASE_URL`.
- `contracts/schemas`: JSON Schema cho raw protein input event và prediction result event.
- `infra/cassandra`: CQL schema ban đầu cho request status và latest prediction.
- `ml/inference`: module placeholder cho preprocess, feature builder, predictor và postprocess.
- `docker-compose.yml` và `docker/`: local/dev stack cho Serving API, frontend, Kafka, RabbitMQ, Cassandra và Spark.
- `apps/ingestion_api`, `jobs/spark_streaming`, `scripts`: placeholder để triển khai các giai đoạn tiếp theo.

Tài liệu kế hoạch chi tiết nằm ở [task.md](task.md), ghi chú kiến trúc ở [docs/architecture.md](docs/architecture.md).

## Kiến trúc tổng quan

```text
Data source / API / CAFA-6 replay
        |
        v
Ingestion API
        |
        v
Kafka topics --------------+
        |                  |
        v                  v
Spark Structured       RabbitMQ control plane
Streaming              retry / orchestration
        |
        v
ML inference package
        |
        v
Cassandra
  |-- raw events
  |-- request status
  |-- latest prediction
  |-- prediction history
  |-- metrics
        |
        v
Serving API + Frontend dashboard
```

## Cấu trúc thư mục

```text
.
|-- apps/
|   |-- ingestion_api/        # service nhận dữ liệu đầu vào, hiện là placeholder
|   `-- serving_api/          # FastAPI serving + JWT auth demo
|-- contracts/
|   `-- schemas/              # JSON Schema cho event contract
|-- docs/                     # ghi chú kiến trúc
|-- frontend/                 # React dashboard
|-- docker/                   # Dockerfile, Nginx config và init script cho local stack
|-- infra/
|   |-- cassandra/            # schema CQL
|   `-- docker/               # compose placeholder cũ, giữ để tham khảo
|-- jobs/
|   `-- spark_streaming/      # Spark Structured Streaming placeholder
|-- ml/
|   `-- inference/            # preprocess, feature, predict, postprocess placeholder
|-- scripts/                  # script bootstrap/dev
|-- tests/                    # nơi đặt unit/integration/contract test
|-- docker-compose.yml        # compose chính chạy full local stack
|-- .env.example              # mẫu cấu hình Docker Compose
|-- pyproject.toml
`-- task.md
```

## Yêu cầu môi trường

- Python `>= 3.11`
- Node.js và npm cho frontend
- Docker/Docker Compose nếu muốn phát triển phần hạ tầng local

## Chạy Serving API

Từ thư mục root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
uvicorn apps.serving_api.src.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Biến môi trường chính:

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `JWT_SECRET` | `dev-only-change-me` | Khóa ký JWT, cần đổi khi chạy môi trường thật |
| `JWT_EXPIRES_SECONDS` | `3600` | Thời gian sống của access token |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Origin frontend được phép gọi API |
| `HOST` | `0.0.0.0` | Host khi chạy qua `python apps/serving_api/src/main.py` |
| `PORT` | `8000` | Port khi chạy qua entrypoint Python |
| `RELOAD` | `false` | Bật/tắt reload khi chạy qua entrypoint Python |

## Tài khoản demo

| Username | Password | Role | Quyền |
| --- | --- | --- | --- |
| `viewer` | `viewer123` | `viewer` | Xem dashboard, request status, prediction |
| `operator` | `operator123` | `viewer`, `operator` | Quyền viewer và tạo inference request |
| `admin` | `admin123` | `viewer`, `operator`, `admin` | Toàn quyền demo hiện có |

## API chính

| Method | Endpoint | Auth | Mô tả |
| --- | --- | --- | --- |
| `GET` | `/health` | Không | Kiểm tra service |
| `POST` | `/api/auth/login` | Không | Đăng nhập và nhận bearer token |
| `GET` | `/api/auth/me` | Bearer token | Lấy thông tin user hiện tại |
| `POST` | `/api/auth/logout` | Bearer token | Revoke token trong phiên chạy API |
| `GET` | `/api/metrics/pipeline/summary` | `viewer` trở lên | Dashboard summary |
| `POST` | `/api/inference-requests` | `operator` hoặc `admin` | Tạo request inference mới |
| `GET` | `/api/inference-requests/{request_id}` | `viewer` trở lên | Tra cứu trạng thái request |
| `GET` | `/api/proteins/{protein_id}/latest-prediction` | `viewer` trở lên | Lấy prediction mới nhất theo protein |

Ví dụ đăng nhập:

```powershell
$body = @{ username = "operator"; password = "operator123" } | ConvertTo-Json
$login = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/auth/login `
  -ContentType "application/json" `
  -Body $body

$token = $login.access_token
Invoke-RestMethod `
  -Headers @{ Authorization = "Bearer $token" } `
  http://localhost:8000/api/metrics/pipeline/summary
```

## Chạy Frontend

Từ thư mục `frontend`:

```powershell
npm install
npm run dev
```

Mặc định frontend dùng mock API nếu chưa cấu hình `VITE_API_BASE_URL`. Để gọi Serving API thật:

```powershell
$env:VITE_API_BASE_URL = "http://localhost:8000"
npm run dev
```

Các màn hình hiện có:

- Login
- Overview dashboard
- Submit protein request
- Request status
- Latest prediction

## Event contracts

Schema hiện có:

- [contracts/schemas/raw_input_event.json](contracts/schemas/raw_input_event.json): event đầu vào gồm `request_id`, `protein_id`, `sequence`, `source`, `event_time`, `metadata`.
- [contracts/schemas/prediction_result_event.json](contracts/schemas/prediction_result_event.json): event kết quả gồm `request_id`, `protein_id`, `predicted_at`, `model_version`, `predicted_terms`, `confidence_summary`.

Các producer/consumer nên validate payload theo các schema này trước khi ghi hoặc đọc từ streaming backbone.

## Cassandra schema

Schema ban đầu nằm ở [infra/cassandra/schema.cql](infra/cassandra/schema.cql):

- `protein_rt.request_status_by_id`: tra cứu trạng thái request theo `request_id`.
- `protein_rt.latest_prediction_by_protein`: lấy kết quả dự đoán mới nhất theo `protein_id`.

Kế hoạch đầy đủ trong `task.md` còn đề xuất thêm các bảng cho raw events, prediction history, failed requests, metrics window và feature snapshot.

## Docker Compose

Compose chính nằm ở [docker-compose.yml](docker-compose.yml), dùng `.env` ở root và các file trong [docker/](docker/). Stack local/dev bao gồm:

- `serving-api`: FastAPI demo trên port `8000`.
- `frontend`: React/Vite build static serve qua Nginx trên port `5173`.
- `kafka` + `kafka-init`: Kafka KRaft local và bootstrap topic `raw_protein_input`, `validated_protein_input`, `inference_request`, `prediction_result`, `dead_letter`.
- `rabbitmq`: RabbitMQ + Management UI.
- `cassandra` + `cassandra-init`: Cassandra local và bootstrap keyspace/table từ [infra/cassandra/schema.cql](infra/cassandra/schema.cql).
- `spark-master` + `spark-worker`: Spark local cluster cho job streaming sau này.

Chạy toàn bộ stack từ root repo:

```powershell
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8000/health
```

Các URL chính:

| Service | URL |
| --- | --- |
| Frontend | `http://localhost:5173` |
| Serving API | `http://localhost:8000` |
| RabbitMQ Management | `http://localhost:15672` |
| Spark Master UI | `http://localhost:8080` |
| Spark Worker UI | `http://localhost:8081` |
| Kafka bootstrap từ host | `localhost:9092` |
| Cassandra CQL từ host | `localhost:9042` |

Dừng stack:

```powershell
docker compose down
```

Dừng và xóa volume local:

```powershell
docker compose down -v
```

## Kiểm tra và build

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

Lưu ý: thư mục `tests` hiện chưa có test thực thi, mới là nơi chuẩn bị cho unit test, integration test và contract test.

## Lộ trình phát triển

1. Hoàn thiện event contract và test validate schema.
2. Triển khai Ingestion API để nhận protein sequence và publish raw event vào Kafka.
3. Kết nối Ingestion API/Spark job với Docker Compose local stack đã có.
4. Mở rộng Cassandra schema theo query pattern trong `task.md`.
5. Xây Spark Structured Streaming job đọc Kafka, validate event, tạo feature và ghi Cassandra.
6. Đóng gói ML inference từ baseline/solution CAFA-6 thay cho placeholder hiện tại.
7. Kết nối Serving API với Cassandra thay vì dữ liệu in-memory.
8. Bổ sung prediction history, retry failed request, metrics vận hành và test độ tin cậy.

## License

Xem [LICENSE](LICENSE).
