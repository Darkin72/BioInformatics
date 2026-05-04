# Stack Docker local

Thư mục này chứa cấu hình Docker cho môi trường local/dev của dự án:

- `backend/Dockerfile`: đóng gói FastAPI Serving API.
- `frontend/Dockerfile`: build React/Vite và phục vụ bằng Nginx.
- `frontend/nginx.conf`: cấu hình SPA fallback cho frontend.
- `kafka/create-topics.sh`: tạo các topic theo `task.md`.
- `cassandra/init-schema.sh`: nạp `infra/cassandra/schema.cql` vào Cassandra.
- `postgres/init.sql`: tạo schema PostgreSQL ban đầu cho metadata/quản trị.

Từ root repo, chạy các service chính:

```powershell
docker compose up -d --build
```

Nếu mới tạo volume hoặc vừa chạy `docker compose down -v`, bootstrap topic/schema bằng init job chạy một lần:

```powershell
docker compose run --rm kafka-init
docker compose run --rm cassandra-init
```

Hai container init này sẽ tự bị xóa sau khi chạy xong vì dùng `--rm`.

Sau khi stack sẵn sàng:

- Frontend: http://localhost:5173
- Serving API: http://localhost:8000
- API health: http://localhost:8000/health
- RabbitMQ Management: http://localhost:15672
- PostgreSQL: `localhost:5432`
- Spark Master UI: http://localhost:8080
- Spark Worker UI: http://localhost:8081
- Kafka external bootstrap: `localhost:9092`
- Cassandra CQL: `localhost:9042`

Tài khoản demo của frontend/API:

| Tên đăng nhập | Mật khẩu |
| --- | --- |
| `viewer` | `viewer123` |
| `operator` | `operator123` |
| `admin` | `admin123` |

Kiểm tra nhanh:

```powershell
docker compose ps
Invoke-RestMethod http://localhost:8000/health
```

Dừng stack:

```powershell
docker compose down
```

Xóa cả volume local:

```powershell
docker compose down -v
```
