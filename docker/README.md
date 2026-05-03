# Docker local stack

Thu muc nay chua cau hinh Docker cho moi truong local/dev cua du an:

- `backend/Dockerfile`: dong goi FastAPI Serving API.
- `frontend/Dockerfile`: build React/Vite va serve bang Nginx.
- `frontend/nginx.conf`: cau hinh SPA fallback cho frontend.
- `kafka/create-topics.sh`: tao cac topic theo `task.md`.
- `cassandra/init-schema.sh`: nap `infra/cassandra/schema.cql` vao Cassandra.

Tu root repo, chay:

```powershell
docker compose up -d --build
```

Sau khi stack san sang:

- Frontend: http://localhost:5173
- Serving API: http://localhost:8000
- API health: http://localhost:8000/health
- RabbitMQ Management: http://localhost:15672
- Spark Master UI: http://localhost:8080
- Spark Worker UI: http://localhost:8081
- Kafka external bootstrap: `localhost:9092`
- Cassandra CQL: `localhost:9042`

Tai khoan demo cua frontend/API:

| Username | Password |
| --- | --- |
| `viewer` | `viewer123` |
| `operator` | `operator123` |
| `admin` | `admin123` |

Kiem tra nhanh:

```powershell
docker compose ps
Invoke-RestMethod http://localhost:8000/health
```

Dung stack:

```powershell
docker compose down
```

Xoa ca volume local:

```powershell
docker compose down -v
```
