# Hạ tầng

Hạ tầng local/dev hiện nằm trong các manifest Kubernetes tại [k8s](k8s).

```powershell
.\scripts\k8s-build-images.ps1
kubectl apply -k infra/k8s
```

Stack Kubernetes chạy Kafka, RabbitMQ, PostgreSQL, Cassandra, Spark, các backend service, worker, frontend và các bootstrap Job để tạo Kafka topic/Cassandra schema.

Các file Docker Compose cũ vẫn được giữ lại làm tham chiếu legacy trong [docker](docker) và ở root repo.
