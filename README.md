# BioInformatics

Khung monorepo toi gian cho du an du doan chuc nang protein theo thoi gian thuc.

## Muc tieu

Du an duoc to chuc quanh cac thanh phan chinh:

- `apps/ingestion_api`: nhan request hoac replay event dau vao
- `apps/serving_api`: tra cuu trang thai va ket qua prediction
- `jobs/spark_streaming`: pipeline Spark Structured Streaming
- `ml/inference`: cac module preprocess, feature, inference, postprocess
- `contracts/schemas`: JSON schema cho event contracts
- `infra`: docker compose, CQL schema, bootstrap ha tang
- `docs`: tai lieu kien truc va planning
- `scripts`: script ho tro local/dev
- `tests`: noi dat test sau nay

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

## Huong mo rong tiep theo

1. Chot data contract trong `contracts/schemas`.
2. Hoan thien `infra/docker/docker-compose.yml` cho Kafka, RabbitMQ, Cassandra, Spark.
3. Implement flow ingest -> Kafka -> Spark -> Cassandra.
4. Dong goi inference module trong `ml/inference`.
