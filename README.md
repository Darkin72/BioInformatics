# BioInformatics Big Data Realtime Protein Function Prediction

Dự án xây dựng một hệ thống **Big Data realtime** để nhận luồng sequence protein, xử lý streaming, gọi mô hình CAFA-6 và phục vụ kết quả dự đoán chức năng protein gần thời gian thực.

Điểm trọng tâm của bài không nằm ở một API đơn lẻ, mà ở cách tổ chức một pipeline dữ liệu lớn có đủ các lớp: ingestion, message backbone, stream processing, distributed serving store, metadata store, dashboard, benchmark tải và triển khai bằng Kubernetes.

## Hệ thống

Hệ thống được thiết kế theo các đặc trưng chính của môn Big Data:

- **Volume**: dữ liệu protein, event trạng thái, prediction history, metrics và audit log được ghi liên tục; benchmark có kịch bản `360000` request với `3,600,000` sequence record.
- **Velocity**: Kafka nhận luồng event tốc độ cao; Spark Structured Streaming xử lý theo micro-batch; dashboard nhận cập nhật gần realtime qua SSE.
- **Variety**: dữ liệu gồm protein sequence, metadata request, GO term prediction, trạng thái pipeline, metric vận hành, DLQ và audit.
- **Scalability**: Kafka, Spark, Cassandra và worker service được tách lớp để có thể scale ngang theo bottleneck.
- **Fault tolerance**: pipeline có dead-letter topic, retry/control-plane qua RabbitMQ, trạng thái request trong Cassandra và cơ chế replay để phục hồi hoặc kiểm thử lỗi.
- **Serving theo access pattern**: Cassandra được thiết kế theo query pattern thay vì chuẩn hóa kiểu SQL, phù hợp workload append-heavy/time-series.

## Bài toán

Nguồn dữ liệu gốc lấy cảm hứng từ **CAFA-6 Protein Function Prediction**. Dữ liệu batch/competition được biến thành ngữ cảnh realtime bằng cách phát lại sequence thành stream hoặc nhận sequence trực tiếp qua API.

Hệ thống cần hỗ trợ:

1. Nhận protein sequence từ API hoặc replay stream.
2. Validate, chuẩn hóa và khử trùng lặp event đầu vào.
3. Gọi pipeline inference CAFA-6 để dự đoán GO terms.
4. Ghi raw event, trạng thái, prediction, history, metrics và failure vào Cassandra.
5. Lưu metadata quản trị, model registry, replay campaign và audit vào PostgreSQL.
6. Cho phép frontend/API tra cứu request status, latest prediction, prediction history và dashboard metric.
7. Hỗ trợ stress test, replay và quan sát pipeline dưới tải lớn.

## Kiến trúc tổng quan

```text
User / Replay / Batch Simulation
        |
        v
Serving API / Ingestion API
        |
        +-------------------> RabbitMQ
        |                     - command/control events
        |                     - retry queue
        |                     - notification orchestration
        v
      Kafka
        - protein.raw-input.v1
        - protein.validated-input.v1
        - protein.prediction-result.v1
        - protein.dead-letter.v1
        |
        v
Spark Structured Streaming
        - validation
        - normalization
        - deduplication
        - micro-batch inference
        - post-processing
        |
        +-------------------> Modal CAFA-6 GPU endpoint
        |
        +-------------------> Cassandra
        |                     - raw events
        |                     - request status
        |                     - latest prediction
        |                     - prediction history
        |                     - pipeline metrics
        |                     - failed requests
        |
        +-------------------> Kafka result/DLQ topics
        |
        v
Serving API + Notification Service + Frontend Dashboard

PostgreSQL song song lưu metadata quản trị, model registry, replay campaign và audit log.
```

## Vai trò các công nghệ

| Công nghệ                  | Vai trò trong hệ thống Big Data                                                                          |
| -------------------------- | -------------------------------------------------------------------------------------------------------- |
| Kafka                      | Data-plane streaming backbone cho luồng event tốc độ cao, topic result và dead-letter.                   |
| RabbitMQ                   | Control-plane cho retry, command, notification và orchestration giữa service.                            |
| Spark Structured Streaming | Xử lý stream theo micro-batch: validate, normalize, deduplicate, gọi inference và ghi sink.              |
| Cassandra                  | Distributed serving store cho workload ghi nhiều, time-series, event log và prediction history.          |
| PostgreSQL                 | Metadata store có transaction/constraint rõ ràng cho quản trị, model registry, replay campaign và audit. |
| Modal                      | GPU model serving cho CAFA-6 ensemble/streaming endpoint.                                                |
| Kubernetes                 | Điều phối service, worker, stateful dependency, bootstrap job và môi trường demo local.                  |
| React/Vite                 | Dashboard realtime cho trạng thái request, metric pipeline và kết quả dự đoán.                           |

## Vì sao Cassandra là trung tâm lưu trữ Big Data

Theo định hướng trong [task.md](task.md), Cassandra là thành phần cần nhấn mạnh vì phù hợp nhất với workload chính của bài toán:

- Dữ liệu có tính **event-driven**, **append-heavy** và phát sinh liên tục.
- Query chính là tra cứu theo `request_id`, `protein_id`, time bucket, status bucket và metric window.
- Prediction history, request timeline và pipeline metrics là dữ liệu time-series cần ghi nhanh.
- Thiết kế bảng theo access pattern giúp API/dashboard đọc trực tiếp, tránh join nặng trong đường realtime.
- Khi triển khai cluster thật, Cassandra có thể dùng replication factor và tunable consistency để cân bằng throughput, latency và độ sẵn sàng.

Các bảng Cassandra chính nằm trong [infra/cassandra/schema.cql](infra/cassandra/schema.cql):

- `raw_protein_events`: raw audit/replay event.
- `request_status_by_id`: tra cứu trạng thái request.
- `requests_by_day`, `requests_by_status_window`, `requests_by_user_window`: phục vụ dashboard/admin query.
- `latest_prediction_by_protein`: kết quả mới nhất theo protein.
- `prediction_history_by_protein`: lịch sử dự đoán theo thời gian.
- `prediction_by_request`: kết quả theo request.
- `failed_requests_by_time`: vận hành, retry và failure analysis.
- `pipeline_metrics_by_window`: metric theo time window.

## Luồng dữ liệu chính

### Luồng tạo request inference

```text
POST /api/inference-requests
  -> Serving API validate payload + auth
  -> ghi trạng thái request ban đầu
  -> publish command qua RabbitMQ
  -> worker gọi CAFA-6 Modal endpoint
  -> ghi prediction/status vào Cassandra
  -> Notification Service phát SSE cho dashboard
```

### Luồng streaming/replay

```text
Replay/API event
  -> Kafka protein.raw-input.v1
  -> Spark Structured Streaming
  -> validate + normalize + deduplicate
  -> gọi CAFA-6 predict theo micro-batch
  -> ghi Cassandra latest/history/status/metrics
  -> publish protein.prediction-result.v1 hoặc protein.dead-letter.v1
```

## Thành phần trong repo

```text
.
|-- apps/
|   |-- ingestion_api/          # nhận event protein và đẩy vào Kafka/RabbitMQ
|   |-- notification_service/   # consume Kafka, ghi bảng dashboard, phát SSE
|   |-- serving_api/            # auth, API, dashboard summary, inference request
|   |-- inference_worker/       # xử lý RabbitMQ inference_jobs
|   |-- retry_worker/           # xử lý retry_inference
|   `-- replay_service/         # phát lại dữ liệu thành stream/replay workflow
|-- jobs/
|   `-- spark_streaming/        # Spark Structured Streaming job
|-- ml/
|   `-- inference/              # module ML/inference abstraction
|-- contracts/
|   `-- schemas/                # JSON schema cho event contract
|-- infra/
|   |-- cassandra/              # Cassandra schema
|   |-- docker/                 # Docker Compose legacy
|   `-- k8s/                    # Kubernetes stack local
|-- cafa6_modal*/               # Modal endpoint JSON/SSE/graph-aware
|-- frontend/                   # dashboard React/Vite
|-- scripts/                    # stress test, helper script
|-- docs/                       # tài liệu benchmark và thiết kế
`-- tests/
```

## Event contract

Producer/consumer nên validate payload bằng JSON schema trước khi ghi hoặc đọc từ streaming backbone.

- [contracts/schemas/raw_input_event.json](contracts/schemas/raw_input_event.json): event đầu vào gồm `request_id`, `protein_id`, `sequence`, `source`, `event_time`, `metadata`.
- [contracts/schemas/prediction_result_event.json](contracts/schemas/prediction_result_event.json): event kết quả gồm `request_id`, `protein_id`, `predicted_at`, `model_version`, `predicted_terms`, `confidence_summary`.

Ví dụ raw input event:

```json
{
  "request_id": "uuid",
  "protein_id": "protein_a",
  "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
  "source": "api",
  "event_time": "2026-06-04T10:15:00Z",
  "metadata": {
    "dataset_version": "cafa6-v1"
  }
}
```

## Triển khai local bằng Kubernetes

Stack local chính nằm ở [infra/k8s](infra/k8s). Dockerfile vẫn dùng để build image, còn Kubernetes thay Compose để chạy pod, service, persistent volume, healthcheck và bootstrap job.

```powershell
.\scripts\k8s-build-images.ps1
kubectl apply -k infra/k8s
kubectl -n bioinformatics get pods -w
```

Kiểm tra trạng thái:

```powershell
kubectl -n bioinformatics get pods
kubectl -n bioinformatics get jobs
```

Các bootstrap job cần hoàn thành:

- `kafka-init`: tạo topic Kafka.
- `cassandra-init`: nạp schema Cassandra.

## Truy cập local

Dùng port-forward để truy cập ổn định trên Docker Desktop `kind` cluster:

```powershell
kubectl -n bioinformatics port-forward svc/frontend 5174:5173
kubectl -n bioinformatics port-forward svc/serving-api 8001:8000
kubectl -n bioinformatics port-forward svc/notification-service 8004:8003
kubectl -n bioinformatics port-forward svc/rabbitmq 15673:15672
kubectl -n bioinformatics port-forward svc/spark-master 8081:8080
kubectl -n bioinformatics port-forward svc/spark-worker 8082:8081
```

| Thành phần           | URL                            |
| -------------------- | ------------------------------ |
| Frontend             | `http://localhost:5174`        |
| Serving API          | `http://localhost:8001`        |
| Serving API health   | `http://localhost:8001/health` |
| Notification Service | `http://localhost:8004`        |
| RabbitMQ Management  | `http://localhost:15673`       |
| Spark Master UI      | `http://localhost:8081`        |
| Spark Worker UI      | `http://localhost:8082`        |

## Kubernetes và quorum

Để mô phỏng tối thiểu tinh thần distributed system, Docker Desktop `kind` cluster nên chạy **3 node**. Đây là con số tối thiểu theo nguyên tắc quorum `2n + 1` để chịu được 1 node lỗi ở các hệ thống có voting quorum.

Lưu ý: manifest hiện tại là **local/dev stack**. Cluster có thể có 3 node, nhưng Kafka/Cassandra/RabbitMQ trong manifest hiện vẫn chạy cấu hình một replica để nhẹ tài nguyên. Khi chuyển sang staging/production hoặc demo HA thật, cần nâng cấp:

- Kafka KRaft: 3 controller voters/broker phù hợp, replication factor topic là 3, `min.insync.replicas` thường là 2.
- Cassandra: tối thiểu 3 node, keyspace replication factor 3, consistency phù hợp từng use case.
- RabbitMQ: 3 node nếu dùng quorum queues.
- PostgreSQL: dùng operator/managed DB hoặc primary-replica setup.
- App service/worker: replicas từ 2 trở lên, có anti-affinity và resource limit.

## Bật Spark streaming job

Deployment `spark-streaming` có sẵn nhưng mặc định scale về `0` để tránh chạy job nặng khi chỉ cần API/dashboard.

```powershell
kubectl -n bioinformatics scale deployment/spark-streaming --replicas=1
```

Tắt job:

```powershell
kubectl -n bioinformatics scale deployment/spark-streaming --replicas=0
```

## API chính

| Phương thức | Endpoint                               | Xác thực            | Mô tả                           |
| ----------- | -------------------------------------- | ------------------- | ------------------------------- |
| `GET`       | `/health`                              | Không               | Kiểm tra service.               |
| `POST`      | `/api/auth/login`                      | Không               | Đăng nhập và nhận bearer token. |
| `GET`       | `/api/auth/me`                         | Bearer token        | Lấy thông tin user hiện tại.    |
| `POST`      | `/api/auth/logout`                     | Bearer token        | Revoke token.                   |
| `GET`       | `/api/metrics/pipeline/summary`        | `user` hoặc `admin` | Dashboard summary.              |
| `POST`      | `/api/inference-requests`              | `user` hoặc `admin` | Tạo request inference mới.      |
| `GET`       | `/api/inference-requests/{request_id}` | `user` hoặc `admin` | Tra cứu trạng thái request.     |
| `GET`       | `/api/proteins/{protein_id}/requests`  | `user` hoặc `admin` | Lấy request theo protein.       |
| `GET`       | `/api/admin/users/events`              | token query, admin  | SSE danh sách user admin.       |

Ví dụ đăng nhập:

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

## Benchmark và kiểm thử tải

Script [scripts/stress_submit_sequences.py](scripts/stress_submit_sequences.py) giả lập nhiều request sequence gửi đồng thời vào Serving API thật. Đây là phần thể hiện rõ tải Big Data ở lớp API/queue/worker/storage.

Chạy nhanh:

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences `
  --create-samples 20 `
  --concurrency 8 `
  --username admin `
  --password admin123
```

Kịch bản lớn theo tài liệu môn học:

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

Tài liệu chi tiết: [docs/README_360K_REQUESTS_10SEQ.md](docs/README_360K_REQUESTS_10SEQ.md).

Các chỉ số cần quan sát khi benchmark:

- throughput request/giây và sequence/giây.
- latency end-to-end.
- error/failure rate.
- Kafka backlog hoặc consumer lag.
- RabbitMQ queue depth.
- Cassandra write/read latency.
- trạng thái retry và dead-letter.

## Cấu hình quan trọng

| Biến                                | Ý nghĩa                                        |
| ----------------------------------- | ---------------------------------------------- |
| `KAFKA_BOOTSTRAP_SERVERS`           | Kafka bootstrap server cho producer/consumer.  |
| `RABBITMQ_URL`                      | RabbitMQ connection string.                    |
| `CASSANDRA_HOST` / `CASSANDRA_PORT` | Cassandra serving store.                       |
| `CASSANDRA_KEYSPACE`                | Keyspace Cassandra, mặc định `protein_rt`.     |
| `DATABASE_URL`                      | PostgreSQL metadata store.                     |
| `JWT_SECRET`                        | Khóa ký JWT. Cần đổi khi chạy môi trường thật. |
| `CAFA6_PREDICT_URL`                 | Modal endpoint để gọi inference thật.          |
| `CAFA6_HEALTH_URL`                  | Modal health endpoint.                         |
| `CAFA6_TOP_K`                       | Số GO term tối đa trả về.                      |
| `CAFA6_TIMEOUT_SECONDS`             | Timeout khi gọi CAFA-6 endpoint.               |

## Docker Compose legacy

`docker-compose.yml` và [infra/docker/docker-compose.yml](infra/docker/docker-compose.yml) được giữ lại làm tham chiếu legacy/dev cũ. Khi phát triển hoặc demo hiện tại, ưu tiên [infra/k8s](infra/k8s).

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

Kubernetes manifest:

```powershell
kubectl apply -k infra/k8s --dry-run=client
```

## Định hướng mở rộng

Các việc nên làm tiếp để nâng cấp từ demo Big Data sang môi trường HA/production-like:

1. Scale Kafka/Cassandra/RabbitMQ thành cụm 3 node đúng quorum.
2. Thêm monitoring cho Kafka lag, Spark batch duration, Cassandra latency và RabbitMQ backlog.
3. Bổ sung failure testing: kill Kafka broker, Cassandra node, Spark executor, test retry/DLQ.
4. Thêm migration tool cho PostgreSQL, ví dụ Alembic.
5. Tối ưu partition/shard strategy Cassandra bằng benchmark thực tế.
6. Chuẩn hóa dashboard hiệu năng: throughput, latency theo stage, error distribution, prediction volume.

## Tài liệu liên quan

- [infra/k8s/README.md](infra/k8s/README.md): hướng dẫn chạy Kubernetes local.
- [scripts/README.md](scripts/README.md): hướng dẫn stress test.
- [api/README.md](api/README.md): contract CAFA-6 Modal endpoint.
- [contracts/README.md](contracts/README.md): event schema/contract.

## Giấy phép

Xem [LICENSE](LICENSE).
