# Infrastructure

Nơi đặt các file Docker Compose, bootstrap script và schema cho môi trường local/dev.

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```

Stack gồm Kafka, RabbitMQ management UI, Cassandra, ingestion API, serving API và Spark streaming container. Compose tự tạo Kafka topics và chạy `infra/cassandra/schema.cql` khi Cassandra sẵn sàng.

Runbook đầy đủ: [docs/runbook.md](/Users/duongminhquan/Documents/BioInformatics/docs/runbook.md).
