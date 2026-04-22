# Architecture Notes

Ban đầu dự án được tách theo 3 luồng lớn:

1. Data plane: ingest -> Kafka -> Spark -> Cassandra
2. Control plane: RabbitMQ cho retry, orchestration, notification
3. Serving plane: API và dashboard đọc từ Cassandra

Tài liệu này là nơi để bổ sung architecture diagram, topic catalog và query patterns.
