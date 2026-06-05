# Stack Kubernetes local

Thư mục này thay thế `docker-compose.yml` ở root repo cho môi trường Kubernetes local trên Docker Desktop cluster kiểu `kind`.

Dockerfile vẫn được dùng để build image. Kubernetes thay Compose để chạy pod, service, persistent volume, health check và bootstrap job.

## Điều kiện trước khi chạy

- Docker Desktop Kubernetes đang bật với cluster type `kind`.
- Docker Desktop dùng containerd image store để cluster local nhìn thấy image vừa build.
- `kubectl` đang trỏ tới context Kubernetes của Docker Desktop.
- Để mô phỏng quorum tối thiểu, nên tạo cluster `kind` với ít nhất 3 worker node. Manifest hiện tại chạy Kafka, Cassandra và RabbitMQ với 3 replica; Kafka topic dùng replication factor 3/min ISR 2, Cassandra keyspace dùng replication factor 3, RabbitMQ dùng cluster 3 node và default quorum queue.

Kiểm tra cluster:

```powershell
kubectl get nodes
kubectl config current-context
```

## Build image local

Từ root repo:

```powershell
.\scripts\k8s-build-images.ps1
```

Các manifest dùng những image local sau:

- `bioinformatics/backend:local`
- `bioinformatics/backend:metrics-local`
- `bioinformatics/frontend:local`
- `bioinformatics/spark-streaming:local`

## Deploy

```powershell
kubectl apply -k infra/k8s
./scripts/k8s-sync-env.ps1 -RestartApps
kubectl get pods -w
```

Lệnh `kubectl apply -k infra/k8s` tạo cấu hình mặc định để stack chạy được trong namespace `default`, để Docker Desktop Dashboard hiển thị trực tiếp ở trang Deployments/Pods mặc định. Lệnh `./scripts/k8s-sync-env.ps1 -RestartApps` đọc file `.env` ở root repo và đồng bộ các biến runtime sang `bioinformatics-config` và `bioinformatics-secret`, tương tự cách Docker Compose dùng `.env`. Không đưa các biến chỉ dành cho host port của Docker Compose như `*_HOST_PORT` vào pod.

Bootstrap job được tạo cho Kafka topic và Cassandra schema:

```powershell
kubectl logs job/kafka-init
kubectl logs job/cassandra-init
```

Các ConfigMap bootstrap được sinh từ file trong `infra/k8s/bootstrap`. Nếu thay đổi `docker/kafka/create-topics.sh`, `docker/cassandra/init-schema.sh`, `infra/cassandra/schema.cql` hoặc `docker/postgres/init.sql`, hãy mirror thay đổi sang `infra/k8s/bootstrap` trước khi apply lại stack Kubernetes.

## Truy cập local

Dùng port-forward để truy cập ổn định trên Docker Desktop `kind` cluster:

```powershell
kubectl port-forward svc/frontend 5174:5173
kubectl port-forward svc/serving-api 8001:8000
kubectl port-forward svc/notification-service 8004:8003
kubectl port-forward svc/rabbitmq 15673:15672
kubectl port-forward svc/spark-master 8081:8080
kubectl port-forward svc/spark-worker 8082:8081
kubectl port-forward svc/prometheus 9090:9090
kubectl port-forward svc/grafana 3000:3000
```

Sau đó mở:

| Thành phần | URL |
| --- | --- |
| Frontend | `http://localhost:5174` |
| Serving API | `http://localhost:8001` |
| Serving API health | `http://localhost:8001/health` |
| Notification service | `http://localhost:8004` |
| RabbitMQ Management | `http://localhost:15673` |
| Spark Master UI | `http://localhost:8081` |
| Spark Worker UI | `http://localhost:8082` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3000` |

Grafana có datasource Prometheus và dashboard `FastAPI Serving API` để theo dõi Serving API. Serving API expose Prometheus metrics ở `/metrics`.

Các service NodePort cũng được khai báo, nhưng Docker Desktop có thể không expose NodePort ra `localhost` tùy cấu hình cluster/network:

| Thành phần | NodePort URL |
| --- | --- |
| Frontend | `http://localhost:30174` |
| Serving API | `http://localhost:30001` |
| Serving API health | `http://localhost:30001/health` |
| Notification service | `http://localhost:30004` |
| Replay service | `http://localhost:30005` |
| RabbitMQ Management | `http://localhost:31673` |
| Spark Master UI | `http://localhost:30081` |
| Spark Worker UI | `http://localhost:30082` |
| Spark Streaming UI | `http://localhost:30040` |
| Prometheus | `http://localhost:30090` |
| Grafana | `http://localhost:30300` |

## Spark streaming job tùy chọn

Deployment `spark-streaming` có sẵn nhưng mặc định scale về `0`, tương đương profile `streaming` cũ trong Compose.

Bật job:

```powershell
kubectl scale deployment/spark-streaming --replicas=1
```

Tắt job:

```powershell
kubectl scale deployment/spark-streaming --replicas=0
```

## Cấu hình

Giá trị mặc định nằm trong `config.yaml`:

- `bioinformatics-config`: lưu cấu hình không nhạy cảm.
- `bioinformatics-secret`: lưu credential và connection string dev-only.

Khi chạy môi trường thật, hãy thay toàn bộ giá trị trong Secret trước khi apply stack.

Các URL Modal CAFA-6 để trống theo mặc định trong manifest. Khi dùng endpoint inference thật, đặt các key sau trong `.env`, rồi chạy lại `./scripts/k8s-sync-env.ps1 -RestartApps`:

- `CAFA6_HEALTH_URL`
- `CAFA6_PREDICT_URL`
- `CAFA6_GRAPH_AWARE_PREDICT_SSE_URL`
- `CAFA6_STREAM_PREDICT_SSE_URL`

## Xóa stack

Xóa toàn bộ Kubernetes resource và persistent volume local của stack:

```powershell
kubectl delete -k infra/k8s
```

Lệnh trên sẽ xóa resource và PVC local của Kafka, RabbitMQ, PostgreSQL và Cassandra khỏi namespace `default`.
