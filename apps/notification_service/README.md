# Notification service

Service này consume event Kafka từ realtime pipeline, ghi các bảng Cassandra phục vụ dashboard, tổng hợp metric và phát cập nhật UI qua Server-Sent Events.

## Nhiệm vụ chính

- Consume các topic `request_status`, `prediction_result` và `dead_letter`.
- Duy trì các bảng Cassandra query cho admin/dashboard view.
- Phát SSE tại `/api/events/dashboard` để frontend nhận cập nhật realtime.

## Endpoint

- `GET /health`: kiểm tra service.
- `GET /api/events/dashboard`: stream SSE cho dashboard.

## Chạy cùng Kubernetes local

Mở service qua port-forward:

```powershell
kubectl -n bioinformatics port-forward svc/notification-service 8004:8003
```

Kiểm tra health:

```powershell
Invoke-RestMethod http://localhost:8004/health
```
