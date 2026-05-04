# Ghi chú kiến trúc

Ban đầu dự án được tách theo 3 luồng lớn:

1. Data plane: `ingest -> Kafka -> Spark -> Cassandra`.
2. Control plane: RabbitMQ cho retry, orchestration và notification.
3. Serving plane: API và dashboard đọc từ Cassandra.

Tài liệu này là nơi bổ sung architecture diagram, topic catalog và query pattern khi các thành phần được triển khai sâu hơn.
