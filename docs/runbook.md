# Docker Runbook

Runbook này chạy toàn bộ hệ thống bằng Docker Compose, ngoại trừ CAFA-6 model endpoint đã được serve trên Modal.

## 1. Cấu hình Modal endpoint

Tạo file env nếu chưa có:

```bash
cp cafa6_modal/.env.example cafa6_modal/.env
```

Điền hai biến:

```env
CAFA6_HEALTH_URL=https://your-workspace--cafa6-health.modal.run
CAFA6_PREDICT_URL=https://your-workspace--cafa6-predict.modal.run
```

Kiểm tra Modal endpoint độc lập từ máy host:

```bash
python cafa6_modal/scripts/call_deployed_endpoint.py --top-k 5
```

## 2. Build và start toàn bộ stack

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```

Compose sẽ chạy:

- Kafka và Kafka topic init
- RabbitMQ
- Cassandra và schema init
- `ingestion-api`
- `serving-api`
- `spark-streaming`

Modal không chạy trong Docker Compose. Container `spark-streaming` đọc `cafa6_modal/.env` và gọi Modal qua HTTP.

## 3. Kiểm tra container

```bash
docker compose -f infra/docker/docker-compose.yml ps
```

Các cổng local:

- Ingestion API: `http://localhost:8001`
- Serving API: `http://localhost:8002`
- Kafka external listener: `localhost:9092`
- RabbitMQ AMQP: `localhost:5672`
- RabbitMQ UI: `http://localhost:15672` với `guest/guest`
- Cassandra: `localhost:9042`
- Spark driver UI: `http://localhost:4040`

Health check API:

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
```

## 4. Kiểm tra Cassandra schema

```bash
docker exec -it protein-cassandra /opt/cassandra/bin/cqlsh -e "DESCRIBE KEYSPACE protein_rt"
```

Nếu init container chạy trước khi Cassandra sẵn sàng, chạy lại schema thủ công:

```bash
docker exec -i protein-cassandra /opt/cassandra/bin/cqlsh < infra/cassandra/schema.cql
```

Sau đó restart app containers:

```bash
docker compose -f infra/docker/docker-compose.yml restart ingestion-api serving-api spark-streaming
```

## 5. Test end-to-end

Gửi một protein:

```bash
curl -s -X POST http://localhost:8001/v1/proteins \
  -H "Content-Type: application/json" \
  -d '{"protein_id":"protein_a","sequence":"MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"}'
```

Gửi với `top_k` riêng cho request:

```bash
curl -s -X POST http://localhost:8001/v1/proteins \
  -H "Content-Type: application/json" \
  -d '{"protein_id":"protein_top_20","sequence":"MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV","top_k":20}'
```

Gửi với `top_k` và `threshold` riêng cho request:

```bash
curl -s -X POST http://localhost:8001/v1/proteins \
  -H "Content-Type: application/json" \
  -d '{"protein_id":"protein_threshold_0","sequence":"MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV","top_k":20,"threshold":0.3}'
```

Nếu không truyền `top_k`, Spark dùng default `CAFA6_TOP_K` trong Docker Compose. Nếu không truyền `threshold`, Spark gửi `null` để Modal dùng threshold mặc định của model endpoint.

Response có `request_id`. Dùng giá trị đó để kiểm tra trạng thái:

```bash
curl http://localhost:8002/v1/requests/<request_id>
```

Tra kết quả đúng theo `request_id`:

```bash
curl http://localhost:8002/v1/requests/<request_id>/prediction
```

Tra cứu latest prediction:

```bash
curl http://localhost:8002/v1/proteins/protein_a/latest
```

Trong Cassandra, bảng latest lưu cả danh sách GO term/score rút gọn và `prediction_rows` dạng JSON string để giữ đủ `aspect` và `name` từ Modal:

```bash
docker exec -it protein-cassandra /opt/cassandra/bin/cqlsh -e \
  "SELECT protein_id, top_terms, top_scores, prediction_rows FROM protein_rt.latest_prediction_by_protein WHERE protein_id='protein_a';"
```

Tra cứu lịch sử:

```bash
curl "http://localhost:8002/v1/proteins/protein_a/history?limit=10"
```

## 6. Debug nhanh

Xem logs toàn stack:

```bash
docker compose -f infra/docker/docker-compose.yml logs -f
```

Xem logs theo service:

```bash
docker compose -f infra/docker/docker-compose.yml logs -f ingestion-api
docker compose -f infra/docker/docker-compose.yml logs -f spark-streaming
docker compose -f infra/docker/docker-compose.yml logs -f serving-api
```

Liệt kê Kafka topics:

```bash
docker exec protein-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

Đọc prediction result topic:

```bash
docker exec -it protein-kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic protein.prediction-result.v1 \
  --from-beginning
```

Xem Cassandra status:

```bash
docker exec -it protein-cassandra nodetool status
```

Kiểm tra bảng status:

```bash
docker exec -it protein-cassandra /opt/cassandra/bin/cqlsh -e \
  "SELECT request_id, protein_id, current_status, stage_name FROM protein_rt.request_status_by_id LIMIT 10;"
```

## 7. Dừng môi trường

Giữ data volume:

```bash
docker compose -f infra/docker/docker-compose.yml down
```

Xóa sạch volume local:

```bash
docker compose -f infra/docker/docker-compose.yml down -v
```
