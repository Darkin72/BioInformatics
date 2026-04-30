# BioInformatics

Khung monorepo tối giản cho dự án dự đoán chức năng protein theo thời gian thực.

## Mục tiêu

Dự án được tổ chức quanh các thành phần chính:

- `apps/ingestion_api`: nhận request hoặc replay event đầu vào
- `apps/serving_api`: tra cứu trạng thái và kết quả dự đoán
- `jobs/spark_streaming`: pipeline Spark Structured Streaming
- `ml/inference`: các module tiền xử lý, tạo đặc trưng, suy luận, hậu xử lý
- `contracts/schemas`: JSON schema cho các event contract
- `infra`: Docker Compose, CQL schema, bootstrap hạ tầng
- `docs`: tài liệu kiến trúc và kế hoạch
- `scripts`: script hỗ trợ local/dev
- `tests`: nơi đặt test sau này

## Cấu trúc thư mục

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

Luồng hiện tại ghép endpoint Modal CAFA-6 vào streaming stack như sau:

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

RabbitMQ nằm ở control-plane: ingestion publish `request.accepted` để sau này gắn retry, notification, reprocess command hoặc workflow orchestration mà không làm nghẽn data-plane Kafka.

### Vai trò công nghệ

- Kafka: backbone stream tốc độ cao cho raw input, prediction result và dead-letter event.
- RabbitMQ: control-plane cho retry, delayed job, notification, command/reprocess.
- Spark Structured Streaming: micro-batch validation, gọi Modal inference, hậu xử lý và ghi serving store.
- Cassandra: kho write-heavy cho raw audit, status, latest prediction, history, failure và metrics.
- Modal: GPU model-serving cho ensemble CAFA-6; hệ thống backend chỉ gửi `{records, top_k, threshold}` và nhận bảng `predictions`.

### Chạy bằng Docker Compose

Hướng dẫn đầy đủ nằm ở [docs/runbook.md](/Users/duongminhquan/Documents/BioInformatics/docs/runbook.md). Toàn bộ backend chạy trong Docker, trừ CAFA-6 Modal endpoint được cấu hình qua `cafa6_modal/.env`.

```bash
cp cafa6_modal/.env.example cafa6_modal/.env
docker compose -f infra/docker/docker-compose.yml up -d --build
```

Điền Modal URL vào `cafa6_modal/.env` trước khi start stack:

```env
CAFA6_HEALTH_URL=https://your-workspace--cafa6-health.modal.run
CAFA6_PREDICT_URL=https://your-workspace--cafa6-predict.modal.run
```

API chạy sẵn trong container:

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
```

Gửi một request:

```bash
curl -X POST http://localhost:8001/v1/proteins \
  -H "Content-Type: application/json" \
  -d '{"protein_id":"protein_a","sequence":"MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"}'
```

Tra cứu kết quả:

```bash
curl http://localhost:8002/v1/requests/<request_id>
curl http://localhost:8002/v1/proteins/protein_a/latest
curl http://localhost:8002/v1/proteins/protein_a/history
```
