# Ingestion API

Service nhận dữ liệu protein từ API hoặc replay service và đẩy event vào streaming backbone.

## Endpoint

- `GET /health`
- `POST /v1/proteins`

Request mẫu:

```json
{
  "protein_id": "protein_a",
  "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
  "top_k": 20,
  "threshold": 0.3,
  "source": "api",
  "metadata": {}
}
```

Service validate sequence, ghi `raw_protein_events` và `request_status_by_id` vào Cassandra, publish event sang Kafka topic `protein.raw-input.v1`, đồng thời gửi control event `request.accepted` sang RabbitMQ.

`top_k` và `threshold` là optional; nếu có, Spark dùng các giá trị này khi gọi Modal endpoint cho request đó.
