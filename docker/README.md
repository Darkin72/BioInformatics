# Stack Docker local legacy

Kubernetes hiện là stack local/dev ưu tiên của repo này. Từ root repo, dùng hướng dẫn tại [../infra/k8s/README.md](../infra/k8s/README.md):

```powershell
.\scripts\k8s-build-images.ps1
kubectl apply -k infra/k8s
```

Các file Docker Compose vẫn được giữ lại làm tham chiếu legacy.

## Nội dung thư mục

- `backend/Dockerfile`: đóng gói FastAPI backend dùng cho Serving API, replay service và worker.
- `frontend/Dockerfile`: đóng gói React/Vite dev server bằng `npm run dev`.
- `frontend/nginx.conf`: cấu hình SPA fallback cũ, hiện không dùng trong stack dev.
- `kafka/create-topics.sh`: tạo các topic Kafka cần thiết.
- `cassandra/init-schema.sh`: nạp `infra/cassandra/schema.cql` vào Cassandra.
- `postgres/init.sql`: tạo schema PostgreSQL ban đầu cho metadata/quản trị.

## Chạy Compose legacy

Từ root repo:

```powershell
docker compose up -d --build
```

Nếu mới tạo volume hoặc vừa chạy `docker compose down -v`, bootstrap topic/schema bằng init job chạy một lần:

```powershell
docker compose run --rm kafka-init
docker compose run --rm cassandra-init
```

Hai container init này sẽ tự bị xóa sau khi chạy xong vì dùng `--rm`.

## URL legacy

- Frontend: http://localhost:5174
- Serving API: http://localhost:8001
- API health: http://localhost:8001/health
- Notification Service: http://localhost:8004
- RabbitMQ Management: http://localhost:15673
- RabbitMQ AMQP: `localhost:5673`
- PostgreSQL: `localhost:5433`
- Spark Master UI: http://localhost:8081
- Spark Master: `localhost:7078`
- Spark Worker UI: http://localhost:8082
- Kafka external bootstrap: `localhost:9093`
- Cassandra CQL: `localhost:9043`

## Tài khoản demo

| Tên đăng nhập | Mật khẩu |
| --- | --- |
| `viewer` | `viewer123` |
| `operator` | `operator123` |
| `admin` | `admin123` |

## Kiểm tra nhanh

```powershell
docker compose ps
Invoke-RestMethod http://localhost:8001/health
```

## Dừng stack

```powershell
docker compose down
```

Xóa cả volume local:

```powershell
docker compose down -v
```

## Notification service

Stack local có thêm `notification-service` trên port `8003` trong container, expose ra host tại `8004`.

- Consume Kafka topics: `request_status`, `prediction_result`, `dead_letter`.
- Ghi Cassandra serving tables: `requests_by_day`, `requests_by_status_window`, `requests_by_user_window`, `request_timeline_by_id`, `prediction_history_by_protein`, `pipeline_metrics_by_window`.
- Phát SSE cho frontend tại `http://localhost:8004/api/events/dashboard`.

Kiểm tra nhanh:

```powershell
Invoke-RestMethod http://localhost:8004/health
```
