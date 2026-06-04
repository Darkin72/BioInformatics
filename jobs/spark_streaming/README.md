# Spark Streaming Job

Thư mục này chứa pipeline Spark Structured Streaming đọc từ Kafka, xử lý event và ghi vào Cassandra.

Job đọc topic `protein.raw-input.v1`, validate event, gọi `CAFA6_PREDICT_URL` của Modal theo micro-batch, sau đó:

- Ghi latest/history/status vào Cassandra.
- Publish result sang `protein.prediction-result.v1`.
- Ghi lỗi vào `failed_requests_by_time` và publish `protein.dead-letter.v1`.

Modal endpoint nhận payload giống [cafa6_modal/README.md](../../cafa6_modal/README.md): `records`, `top_k`, `threshold`, `include_branch_predictions`.

## Chạy trong Kubernetes local

Deployment `spark-streaming` mặc định có `replicas: 0` để tránh chạy job nặng khi chỉ cần API/dashboard.

Bật job:

```powershell
kubectl -n bioinformatics scale deployment/spark-streaming --replicas=1
```

Tắt job:

```powershell
kubectl -n bioinformatics scale deployment/spark-streaming --replicas=0
```

Mở Spark Streaming UI nếu job đang chạy:

```powershell
kubectl -n bioinformatics port-forward svc/spark-streaming 4040:4040
```
