# Spark Streaming Job

Nơi chứa pipeline Spark Structured Streaming đọc từ Kafka, xử lý event và ghi vào Cassandra.

Job đọc `protein.raw-input.v1`, validate event, gọi `CAFA6_PREDICT_URL` của Modal theo micro-batch, sau đó:

- ghi latest/history/status vào Cassandra
- publish result sang `protein.prediction-result.v1`
- ghi lỗi vào `failed_requests_by_time` và publish `protein.dead-letter.v1`

Modal endpoint nhận payload giống `cafa6_modal/README.md`: `records`, `top_k`, `threshold`, `include_branch_predictions`.
