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

## Hướng mở rộng tiếp theo

1. Chốt data contract trong `contracts/schemas`.
2. Hoàn thiện `infra/docker/docker-compose.yml` cho Kafka, RabbitMQ, Cassandra, Spark.
3. Triển khai luồng `ingest -> Kafka -> Spark -> Cassandra`.
4. Đóng gói inference module trong `ml/inference`.
