# Architecture Notes

Ban đầu dự án được tách theo 3 luồng lớn:

1. Data plane: ingest -> Kafka -> Spark -> Cassandra
2. Control plane: RabbitMQ cho retry, orchestration, notification
3. Serving plane: API và dashboard đọc từ Cassandra

## Data Flow

```text
Client / replay service
  -> Ingestion API
  -> Kafka: protein.raw-input.v1
  -> Spark Structured Streaming
  -> Modal CAFA-6 endpoint
  -> Cassandra + Kafka: protein.prediction-result.v1
  -> Serving API
```

## Topic Catalog

| Topic | Producer | Consumer | Vai trò |
| --- | --- | --- | --- |
| `protein.raw-input.v1` | Ingestion API/replay | Spark | raw canonical input event |
| `protein.validated-input.v1` | Spark | optional downstream | dữ liệu đã validate nếu cần tách stage |
| `protein.prediction-result.v1` | Spark | dashboard/downstream | prediction event sau inference |
| `protein.dead-letter.v1` | Spark/services | retry worker/operator | event lỗi để audit/retry |

## RabbitMQ Catalog

| Exchange/Queue | Vai trò |
| --- | --- |
| `protein.control` topic exchange | command/control-plane event |
| `protein.retry` | retry job hoặc reprocess request lỗi |
| `protein.notification` | notification cho dashboard/operator |
| routing key `request.accepted` | ingestion accepted notification |

## Cassandra Access Patterns

- `request_status_by_id`: `GET /v1/requests/{request_id}`.
- `latest_prediction_by_protein`: `GET /v1/proteins/{protein_id}/latest`.
- `prediction_history_by_protein`: `GET /v1/proteins/{protein_id}/history`.
- `raw_protein_events`: audit/replay theo `(ingest_date, shard_id)`.
- `failed_requests_by_time`: vận hành và retry theo ngày/mã lỗi.
- `pipeline_metrics_by_window`: dashboard throughput/latency.

## Modal Integration

Spark gọi endpoint `CAFA6_PREDICT_URL` bằng payload:

```json
{
  "records": [{ "id": "protein_a", "sequence": "MTEYK..." }],
  "top_k": 50,
  "threshold": null,
  "include_branch_predictions": false
}
```

Output `predictions` được nhóm lại theo `protein_id`, chuyển thành `PredictionResultEvent`, ghi Cassandra latest/history và publish sang `protein.prediction-result.v1`.
