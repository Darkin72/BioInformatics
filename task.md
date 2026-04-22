# Kế hoạch chi tiết xây dựng hệ thống dự đoán chức năng protein theo thời gian thực

## 1. Mục tiêu dự án

Xây dựng một hệ thống **dự đoán chức năng protein theo thời gian thực** từ luồng dữ liệu (data stream), sử dụng:

- **Kafka** làm backbone streaming chính cho dữ liệu vào tốc độ cao
- **RabbitMQ** cho các job/event cần định tuyến linh hoạt, retry, orchestration giữa service
- **Spark Structured Streaming** cho xử lý dòng, feature engineering, scoring, aggregation
- **Cassandra** làm kho dữ liệu Big Data phục vụ ghi/đọc phân tán, độ sẵn sàng cao, truy vấn time-series/event-centric và serving gần realtime

Nguồn dữ liệu gốc dự kiến:

- **CAFA-6 Protein Function Prediction** trên Kaggle

Hướng phân tích/mô hình:

- Dựa trên **một solution của competition** để tái hiện pipeline suy luận, sau đó đóng gói vào hệ thống realtime

---

## 2. Phạm vi bài toán

### 2.1 Mục tiêu nghiệp vụ

Hệ thống cần hỗ trợ các chức năng sau:

1. Nhận sequence protein từ stream hoặc API ingestion
2. Chuẩn hóa và kiểm tra chất lượng dữ liệu đầu vào
3. Trích xuất feature / embedding / input tensor phù hợp với solution đã chọn
4. Chạy pipeline suy luận để dự đoán chức năng protein (ví dụ GO terms)
5. Ghi kết quả dự đoán, metadata, log xử lý, trạng thái pipeline vào Cassandra
6. Cho phép downstream system hoặc dashboard truy vấn:
   - protein vừa vào hệ thống
   - trạng thái xử lý
   - kết quả dự đoán mới nhất
   - lịch sử prediction theo thời gian
   - thống kê throughput, latency, failure

### 2.2 Ngoài phạm vi giai đoạn 1

1. Tự nghiên cứu mô hình mới vượt benchmark competition
2. Huấn luyện distributed quy mô rất lớn trên cluster GPU riêng
3. Full MLOps production cấp doanh nghiệp đa vùng địa lý
4. Human curation sâu cho kết quả sinh học

---

## 3. Định hướng kiến trúc tổng thể

### 3.1 Luồng kiến trúc đề xuất

```text
Data Source / Batch File / API / Simulation Stream
                |
                v
        Ingestion Service
         |             |
         |             +--> RabbitMQ (job orchestration / retry / notification)
         v
       Kafka Topics
         |
         v
Spark Structured Streaming
  - validation
  - normalization
  - deduplication
  - feature extraction
  - model inference
  - post-processing
         |
         +--> Cassandra (raw events)
         +--> Cassandra (features / predictions / status / metrics)
         +--> Monitoring / Dashboard / Alerting
         +--> Serving API
```

### 3.2 Vai trò từng thành phần

#### Kafka

- Nhận event khối lượng lớn, throughput cao
- Tách topic theo domain: raw_input, validated_input, inference_request, prediction_result, dead_letter
- Là event backbone cho pipeline streaming

#### RabbitMQ

- Dùng cho các tác vụ điều phối cần routing tinh hơn
- Phù hợp cho retry queue, delayed job, notification, command queue giữa microservices
- Tách các nghiệp vụ control-plane khỏi data-plane chính

#### Spark Structured Streaming

- Xử lý stream có state
- Chuẩn hóa dữ liệu
- Join metadata
- Tính feature/embedding hoặc gọi service suy luận
- Ghi ra Cassandra và các sink giám sát

#### Cassandra

- Lưu dữ liệu realtime phân tán
- Tối ưu cho write-heavy workload
- Hỗ trợ scale ngang mạnh
- Dùng làm serving store cho lịch sử prediction, trạng thái job, event log, feature snapshot, prediction timeline

---

## 4. Vì sao Cassandra là trọng tâm trong bài toán này

Đây là phần cần nhấn mạnh khi giao việc và thuyết trình kiến trúc.

### 4.1 Điểm mạnh của Cassandra rất phù hợp với bài toán

1. **Write throughput cao, scale ngang tốt**
   - Dòng dữ liệu protein, event xử lý, trạng thái pipeline và kết quả prediction đều phát sinh liên tục
   - Cassandra phù hợp với workload ghi nhiều, đọc theo mẫu truy vấn đã thiết kế trước

2. **High availability và fault tolerance mạnh**
   - Cluster Cassandra có replication giữa nhiều node
   - Một vài node lỗi hệ thống vẫn tiếp tục phục vụ được
   - Rất phù hợp với hệ thống phân tích realtime không được dừng

3. **Tunable consistency**
   - Có thể chọn mức consistency phù hợp theo use case
   - Ví dụ write dùng LOCAL_QUORUM cho dữ liệu prediction quan trọng, ONE cho metrics/log nếu cần throughput cao hơn

4. **Rất hợp với dữ liệu time-series / event log / trạng thái xử lý**
   - Prediction theo timestamp
   - Lịch sử trạng thái theo request
   - Feature snapshot theo version
   - Monitoring counters theo time bucket

5. **Schema wide-column linh hoạt theo access pattern**
   - Dễ mô hình hóa bảng phục vụ dashboard và API query trực tiếp
   - Không cần join phức tạp như hệ quan hệ trong luồng realtime lớn

6. **Khả năng phân tán đa node, đa datacenter**
   - Phù hợp nếu sau này mở rộng thành hệ thống nghiên cứu hoặc production nhiều vùng

### 4.2 Tại sao không chọn RDBMS làm storage chính

RDBMS vẫn hữu ích cho metadata quản trị nhỏ, nhưng không nên là nơi chứa toàn bộ log/prediction stream chính vì:

- write amplification lớn hơn khi ingest tốc độ cao
- scale ngang khó hơn Cassandra
- không tối ưu cho mô hình event-driven append-heavy
- join và lock có thể trở thành bottleneck ở tải lớn

### 4.3 Nguyên tắc thiết kế Cassandra cần quán triệt

1. Thiết kế bảng theo **query pattern**, không theo chuẩn hóa dữ liệu truyền thống
2. Chấp nhận **denormalization có kiểm soát**
3. Chống hotspot bằng partition key hợp lý
4. Quản lý TTL và compaction strategy phù hợp từng bảng
5. Tách bảng raw, serving, metrics, audit để tránh trộn workload

---

## 5. Use case và access pattern cần chốt sớm

Trước khi giao team làm Cassandra schema, phải khóa các truy vấn quan trọng sau.

### 5.1 Use case nghiệp vụ

1. Nhận sequence protein mới và tạo request xử lý
2. Xem trạng thái xử lý của một request
3. Xem kết quả dự đoán mới nhất của một protein
4. Xem lịch sử dự đoán của một protein theo thời gian
5. Xem top protein lỗi trong 1 khoảng thời gian
6. Xem throughput/latency theo phút hoặc giờ
7. Reprocess một request lỗi
8. Truy xuất raw event để audit/debug

### 5.2 Truy vấn chính

1. `get_request_status(request_id)`
2. `get_latest_prediction(protein_id)`
3. `get_prediction_history(protein_id, date_range)`
4. `list_recent_requests_by_status(status, time_bucket)`
5. `get_raw_events_by_ingest_date(date, shard)`
6. `get_pipeline_metrics(metric_name, time_bucket)`
7. `get_failed_requests(time_bucket)`

---

## 6. Mô hình dữ liệu Cassandra đề xuất

> Lưu ý: đây là mô hình khởi đầu để giao việc. Team có thể tinh chỉnh sau khi benchmark.

### 6.1 Keyspace

#### `protein_rt`

- Replication strategy: NetworkTopologyStrategy
- Replication factor: 3 (môi trường cluster chuẩn)

### 6.2 Bảng 1: raw_protein_events

Lưu toàn bộ event đầu vào để audit/replay.

**Mục đích**

- debug
- replay stream
- kiểm tra input gốc

**Partitioning đề xuất**

- partition key: `(ingest_date, shard_id)`
- clustering key: `(event_ts, request_id)`

**Cột gợi ý**

- ingest_date
- shard_id
- event_ts
- request_id
- protein_id
- source_type
- sequence_raw
- source_payload
- checksum
- producer_id

**Ghi chú**

- Dùng TTL nếu không cần giữ lâu dài
- shard_id để tránh partition quá lớn

### 6.3 Bảng 2: request_status_by_id

Tra cứu nhanh trạng thái request.

**Primary key**

- partition key: `request_id`

**Cột**

- request_id
- protein_id
- created_at
- updated_at
- current_status
- error_code
- error_message
- stage_name
- retry_count
- model_version
- feature_version

### 6.4 Bảng 3: latest_prediction_by_protein

Bảng serving để lấy kết quả mới nhất.

**Primary key**

- partition key: `protein_id`

**Cột**

- protein_id
- request_id
- predicted_at
- model_version
- top_terms
- top_scores
- confidence_summary
- explanation_ref
- embedding_ref

### 6.5 Bảng 4: prediction_history_by_protein

Lưu lịch sử dự đoán theo thời gian.

**Primary key**

- partition key: `protein_id`
- clustering key: `predicted_at DESC, request_id`

**Cột**

- protein_id
- predicted_at
- request_id
- model_version
- feature_version
- predicted_terms
- score_map
- threshold_used
- latency_ms

### 6.6 Bảng 5: failed_requests_by_time

Hỗ trợ vận hành và retry.

**Primary key**

- partition key: `(failure_date, status_code)`
- clustering key: `(failed_at DESC, request_id)`

**Cột**

- failure_date
- status_code
- failed_at
- request_id
- protein_id
- stage_name
- reason
- retryable

### 6.7 Bảng 6: pipeline_metrics_by_window

Lưu metrics theo bucket thời gian.

**Primary key**

- partition key: `(metric_date, metric_name)`
- clustering key: `(window_start DESC)`

**Cột**

- metric_date
- metric_name
- window_start
- window_end
- metric_value
- tags

### 6.8 Bảng 7: feature_snapshot_by_request

Lưu snapshot feature hoặc reference đến object storage.

**Primary key**

- partition key: `request_id`

**Cột**

- request_id
- protein_id
- feature_version
- generated_at
- feature_hash
- feature_payload_ref
- embedding_vector_ref

---

## 7. Mapping dữ liệu CAFA-6 vào hệ thống realtime

### 7.1 Cách dùng dataset competition

Do CAFA-6 thiên về dữ liệu competition/batch, team cần biến nó thành ngữ cảnh realtime bằng 3 lớp:

1. **Offline preparation layer**
   - làm sạch dữ liệu sequence
   - xây mapping protein_id / ontology / label
   - tái hiện pipeline preprocessing của solution đã chọn

2. **Streaming simulation layer**
   - phát tuần tự dữ liệu từ CAFA-6 thành stream giả lập
   - cho phép cấu hình tốc độ: 10/s, 100/s, 1000/s
   - gắn event time, source id, replay id

3. **Online inference layer**
   - sequence đi qua pipeline như dữ liệu thật
   - tạo output prediction gần realtime

### 7.2 Nguồn event đầu vào cần chuẩn hóa

Mỗi event nên có format thống nhất:

```json
{
  "request_id": "uuid",
  "protein_id": "string",
  "sequence": "MENDEL...",
  "source": "cafa6_replay",
  "event_time": "2026-04-22T10:15:00Z",
  "metadata": {
    "species": "optional",
    "split": "train/valid/test",
    "dataset_version": "v1"
  }
}
```

---

## 8. Chọn solution competition để tích hợp

### 8.1 Tiêu chí chọn

Team ML/Data Science cần chọn solution theo các tiêu chí:

1. Có public notebook/repo hoặc mô tả đủ rõ
2. Dễ tái hiện feature engineering
3. Inference time không quá nặng để đưa vào realtime
4. Hỗ trợ batch scoring hoặc micro-batch scoring
5. Có thể tách thành pipeline độc lập với streaming layer

### 8.2 Cách đóng gói solution

Tách thành 4 lớp:

1. `preprocess_module`
2. `feature_module`
3. `inference_module`
4. `postprocess_module`

Mỗi lớp cần interface rõ ràng để Spark hoặc service gọi được.

### 8.3 Quy tắc kỹ thuật

1. Mọi model version phải có mã phiên bản
2. Mọi feature version phải có mã phiên bản
3. Kết quả phải log đầy đủ input hash, model version, feature version
4. Nếu inference quá nặng, tách sang model serving service riêng

---

## 9. Lộ trình triển khai theo giai đoạn

### Giai đoạn 0 - Chốt bài toán và kiến trúc (1-2 tuần)

#### Mục tiêu

- thống nhất scope
- chốt use case
- chốt kiến trúc logic
- chốt vai trò của từng công nghệ

#### Task nhỏ

**0.1 Phân tích yêu cầu**

- [ ] Viết document mục tiêu hệ thống
- [ ] Liệt kê actor, input, output
- [ ] Liệt kê SLA mong muốn: throughput, latency, availability
- [ ] Chốt các truy vấn API/dashboard cần hỗ trợ

**0.2 Phân tích data source**

- [ ] Tải và kiểm tra cấu trúc CAFA-6
- [ ] Liệt kê file nào dùng cho training / validation / replay
- [ ] Xác định schema sequence, label, ontology
- [ ] Kiểm tra chất lượng dữ liệu: null, duplicate, invalid sequence

**0.3 Phân tích solution competition**

- [ ] Chọn 2-3 solution khả thi
- [ ] So sánh theo độ khó tái hiện, độ nặng inference, dependency
- [ ] Chọn 1 solution chính và 1 solution backup
- [ ] Viết note pipeline input/output của solution

**0.4 Thiết kế kiến trúc sơ bộ**

- [ ] Vẽ system context diagram
- [ ] Vẽ data flow diagram
- [ ] Xác định topic Kafka
- [ ] Xác định queue RabbitMQ
- [ ] Xác định Cassandra keyspace/table sơ bộ

#### Deliverable

- BRD/technical scope
- Architecture v1
- Danh sách query pattern
- Danh sách solution được chọn

---

### Giai đoạn 1 - Nghiên cứu dữ liệu và chuẩn hóa schema (1-2 tuần)

#### Mục tiêu

- hiểu sâu dữ liệu competition
- có canonical schema cho toàn hệ thống

#### Task nhỏ

**1.1 Khảo sát dữ liệu CAFA-6**

- [ ] Thống kê số lượng protein
- [ ] Thống kê độ dài sequence
- [ ] Thống kê phân bố label/GO term
- [ ] Xác định trường nào cần cho inference realtime

**1.2 Chuẩn hóa schema event**

- [ ] Thiết kế JSON schema cho raw input event
- [ ] Thiết kế JSON schema cho validated event
- [ ] Thiết kế JSON schema cho prediction result
- [ ] Thiết kế schema cho dead-letter event

**1.3 Chuẩn hóa id và metadata**

- [ ] Quy ước request_id
- [ ] Quy ước protein_id
- [ ] Quy ước model_version / feature_version
- [ ] Quy ước timestamp và timezone

**1.4 Data contracts**

- [ ] Viết tài liệu contract producer-consumer
- [ ] Định nghĩa rule validate sequence
- [ ] Định nghĩa checksum/hash strategy

#### Deliverable

- data dictionary
- event schemas
- contract spec v1

---

### Giai đoạn 2 - Thiết kế hạ tầng streaming và messaging (2 tuần)

#### Mục tiêu

- dựng backbone Kafka + RabbitMQ
- định nghĩa luồng event rõ ràng

#### Task nhỏ

**2.1 Kafka design**

- [ ] Tạo danh sách topic cần thiết
- [ ] Định nghĩa retention cho từng topic
- [ ] Định nghĩa số partition ban đầu
- [ ] Thiết kế key cho producer để phân phối đều partition
- [ ] Thiết kế DLQ strategy

**2.2 RabbitMQ design**

- [ ] Xác định queue cho command/control/retry
- [ ] Chọn loại exchange: direct/topic/fanout
- [ ] Thiết kế routing key convention
- [ ] Thiết kế retry queue và poison message handling
- [ ] Thiết kế ack/requeue policy

**2.3 Streaming replay service**

- [ ] Viết service phát lại dữ liệu CAFA-6 thành stream
- [ ] Hỗ trợ cấu hình tốc độ phát
- [ ] Hỗ trợ pause/resume
- [ ] Hỗ trợ inject lỗi để test

**2.4 Local/dev infrastructure**

- [ ] Viết Docker Compose cho Kafka, RabbitMQ, Cassandra, Spark
- [ ] Viết script bootstrap topic/queue/keyspace
- [ ] Kiểm tra end-to-end dev environment

#### Deliverable

- topic/queue catalog
- replay service v1
- local stack chạy được

---

### Giai đoạn 3 - Thiết kế và triển khai Cassandra (2-3 tuần)

#### Mục tiêu

- biến Cassandra thành serving + audit + monitoring store chính

#### Task nhỏ

**3.1 Chốt query-driven schema**

- [ ] Review tất cả access pattern với team backend
- [ ] Tính cardinality cho partition key
- [ ] Dự đoán kích thước partition
- [ ] Chốt bảng và khóa chính

**3.2 Thiết kế bảng**

- [ ] Viết CQL cho keyspace
- [ ] Viết CQL cho bảng raw events
- [ ] Viết CQL cho bảng request status
- [ ] Viết CQL cho bảng latest prediction
- [ ] Viết CQL cho bảng prediction history
- [ ] Viết CQL cho bảng failed requests
- [ ] Viết CQL cho bảng metrics

**3.3 Chính sách vận hành Cassandra**

- [ ] Chọn replication factor
- [ ] Chọn consistency level cho từng luồng ghi/đọc
- [ ] Chọn compaction strategy từng bảng
- [ ] Chọn TTL cho bảng raw/log/metrics
- [ ] Thiết kế backup/restore sơ bộ

**3.4 Benchmark Cassandra**

- [ ] Benchmark write throughput
- [ ] Benchmark read latency cho query chính
- [ ] Test hotspot partition
- [ ] Test node failure scenario
- [ ] Tối ưu partition/shard strategy nếu cần

**3.5 Data access layer**

- [ ] Viết repository/service cho Cassandra
- [ ] Chuẩn hóa retry policy phía application
- [ ] Thêm idempotency logic cho ghi prediction
- [ ] Viết integration test cho từng bảng

#### Deliverable

- Cassandra schema v1
- benchmark report
- data access layer v1

---

### Giai đoạn 4 - Xây pipeline Spark Structured Streaming (2-4 tuần)

#### Mục tiêu

- có pipeline xử lý realtime từ Kafka sang Cassandra

#### Task nhỏ

**4.1 Input ingestion**

- [ ] Đọc raw event từ Kafka
- [ ] Parse JSON schema
- [ ] Reject event lỗi format
- [ ] Ghi event lỗi vào DLQ

**4.2 Validation & normalization**

- [ ] Validate protein sequence
- [ ] Normalize metadata
- [ ] Khử duplicate theo request_id/checksum
- [ ] Gắn processing timestamp

**4.3 Feature preparation**

- [ ] Chuẩn hóa input cho solution đã chọn
- [ ] Sinh feature/embedding
- [ ] Cache hoặc reference feature snapshot
- [ ] Ghi feature metadata vào Cassandra

**4.4 Inference orchestration**

- [ ] Gọi module inference trực tiếp trong Spark hoặc qua service
- [ ] Hỗ trợ micro-batch scoring
- [ ] Gắn model_version
- [ ] Bắt lỗi timeout/failure

**4.5 Post-processing**

- [ ] Chuẩn hóa output thành danh sách GO term + score
- [ ] Áp threshold hoặc ranking rule
- [ ] Sinh confidence summary
- [ ] Ghi prediction vào Cassandra

**4.6 Operational metrics**

- [ ] Tính latency từng stage
- [ ] Tính throughput theo micro-batch
- [ ] Tính error rate
- [ ] Ghi metrics về Cassandra và monitoring sink

#### Deliverable

- Spark job v1
- pipeline chạy từ topic input đến Cassandra
- test report cho micro-batch

---

### Giai đoạn 5 - Đóng gói solution ML/inference (2-3 tuần)

#### Mục tiêu

- tái hiện được solution competition ở mức inference ổn định

#### Task nhỏ

**5.1 Reproduce baseline**

- [ ] Clone/viết lại pipeline solution
- [ ] Xác minh input/output format
- [ ] Chạy thử offline trên sample data
- [ ] So sánh kết quả với baseline kỳ vọng

**5.2 Tách module hóa**

- [ ] Tách preprocess function
- [ ] Tách feature builder
- [ ] Tách predictor
- [ ] Tách postprocessor

**5.3 Tối ưu inference**

- [ ] Đo latency từng request
- [ ] Test batch inference vs single inference
- [ ] Cân nhắc cache model trong memory
- [ ] Giảm dependency không cần thiết

**5.4 Versioning & reproducibility**

- [ ] Đóng gói model artifact
- [ ] Gắn model_version
- [ ] Lưu config inference
- [ ] Lưu seed/parameter nếu cần reproducibility

#### Deliverable

- inference package v1
- benchmark latency
- reproducibility note

---

### Giai đoạn 6 - Xây API, dashboard và service layer (2 tuần)

#### Mục tiêu

- cho phép người dùng và hệ thống ngoài truy cập kết quả

#### Task nhỏ

**6.1 Serving API**

- [ ] API tra cứu trạng thái request
- [ ] API lấy latest prediction theo protein_id
- [ ] API lấy prediction history
- [ ] API retry request lỗi
- [ ] API health check

**6.2 Dashboard**

- [ ] Dashboard throughput theo thời gian
- [ ] Dashboard latency từng stage
- [ ] Dashboard error distribution
- [ ] Dashboard số lượng request theo trạng thái
- [ ] Dashboard recent predictions

**6.3 Auth và access control (nếu cần)**

- [ ] Basic authentication cho nội bộ
- [ ] Role phân quyền viewer/operator/admin
- [ ] Audit log cho thao tác retry

#### Deliverable

- API service v1
- dashboard v1

---

### Giai đoạn 7 - Quan sát hệ thống, kiểm thử và hardening (2-3 tuần)

#### Mục tiêu

- đảm bảo hệ thống chạy ổn định dưới tải

#### Task nhỏ

**7.1 Observability**

- [ ] Centralized logging
- [ ] Metric collection cho Kafka/Spark/Cassandra/RabbitMQ
- [ ] Alert rule cho lag, error rate, node down
- [ ] Trace request_id xuyên suốt pipeline

**7.2 Functional testing**

- [ ] Test input hợp lệ
- [ ] Test input lỗi
- [ ] Test duplicate event
- [ ] Test retry path
- [ ] Test DLQ path

**7.3 Performance testing**

- [ ] Test 100 events/s
- [ ] Test 1000 events/s
- [ ] Test burst load
- [ ] Test Cassandra under sustained writes
- [ ] Test Spark restart recovery

**7.4 Failure testing**

- [ ] Kill Kafka broker giả lập
- [ ] Kill Cassandra node giả lập
- [ ] Kill Spark executor giả lập
- [ ] Test RabbitMQ queue backlog
- [ ] Đánh giá data loss / reprocessing behavior

#### Deliverable

- test plan
- performance report
- hardening checklist

---

### Giai đoạn 8 - Triển khai và bàn giao (1-2 tuần)

#### Mục tiêu

- đóng gói tài liệu và đưa vào môi trường demo hoặc production pilot

#### Task nhỏ

**8.1 Deployment**

- [ ] Viết manifest triển khai (Docker/K8s nếu có)
- [ ] Tạo config cho dev/staging/prod
- [ ] Cấu hình secret management
- [ ] Chạy smoke test sau deploy

**8.2 Documentation**

- [ ] Viết README tổng
- [ ] Viết runbook vận hành
- [ ] Viết playbook xử lý lỗi
- [ ] Viết tài liệu schema và query pattern Cassandra

**8.3 Handover**

- [ ] Demo end-to-end
- [ ] Bàn giao source code
- [ ] Bàn giao tài liệu vận hành
- [ ] Chốt backlog phase 2

#### Deliverable

- hệ thống demo/pilot
- full docs
- handover pack

---

## 10. Phân rã công việc theo team

## 10.1 Team Data Engineering

### Trách nhiệm

- ingestion
- Kafka topics
- Spark streaming
- schema event
- replay service

### Task

- [ ] phân tích data source CAFA-6
- [ ] chuẩn hóa event schema
- [ ] dựng replay generator
- [ ] xây Spark ingestion
- [ ] xây validation/dedup stage
- [ ] tích hợp ghi Cassandra
- [ ] benchmark pipeline throughput

## 10.2 Team ML / Data Science

### Trách nhiệm

- chọn solution competition
- tái hiện inference pipeline
- tối ưu feature và scoring

### Task

- [ ] review solution competition
- [ ] tái hiện baseline offline
- [ ] chuẩn hóa preprocess
- [ ] đóng gói inference module
- [ ] benchmark latency
- [ ] xác định ngưỡng post-processing
- [ ] tài liệu hóa model_version và feature_version

## 10.3 Team Backend / Platform

### Trách nhiệm

- API
- service orchestration
- RabbitMQ flow
- Cassandra access layer
- auth

### Task

- [ ] thiết kế REST/gRPC API
- [ ] xây service request tracking
- [ ] tích hợp RabbitMQ cho retry/control
- [ ] xây repository Cassandra
- [ ] triển khai health check và audit
- [ ] viết retry/reprocess endpoint

## 10.4 Team DevOps / SRE

### Trách nhiệm

- cluster
- observability
- deployment
- backup
- resilience

### Task

- [ ] dựng môi trường dev/staging
- [ ] cấu hình monitoring stack
- [ ] cấu hình alerting
- [ ] cấu hình backup Cassandra
- [ ] benchmark cluster behavior
- [ ] viết runbook xử lý sự cố

## 10.5 Team QA

### Trách nhiệm

- test chức năng
- test hiệu năng
- test lỗi

### Task

- [ ] viết test case theo từng stage
- [ ] test duplicate/retry/DLQ
- [ ] test API serving
- [ ] test under load
- [ ] test failover scenario

---

## 11. Backlog chi tiết dạng task nhỏ để giao việc

Dưới đây là backlog rất nhỏ, có thể đưa vào Jira/Trello.

### Epic A - Data understanding

- [ ] A1. Tải toàn bộ dữ liệu CAFA-6
- [ ] A2. Kiểm kê cấu trúc thư mục/file
- [ ] A3. Viết notebook mô tả schema dữ liệu
- [ ] A4. Thống kê sequence length
- [ ] A5. Thống kê missing values
- [ ] A6. Thống kê duplicate protein
- [ ] A7. Viết báo cáo data profiling

### Epic B - Competition solution analysis

- [ ] B1. Tìm 3 solution khả thi
- [ ] B2. Đọc dependency từng solution
- [ ] B3. So sánh mức độ nặng inference
- [ ] B4. Chọn solution chính
- [ ] B5. Viết tài liệu I/O contract của solution
- [ ] B6. Tạo baseline inference script

### Epic C - Event contract

- [ ] C1. Định nghĩa raw_input schema
- [ ] C2. Định nghĩa validated_input schema
- [ ] C3. Định nghĩa prediction_output schema
- [ ] C4. Định nghĩa DLQ schema
- [ ] C5. Định nghĩa error code catalog
- [ ] C6. Viết contract document

### Epic D - Kafka backbone

- [ ] D1. Tạo topic raw_protein_input
- [ ] D2. Tạo topic validated_protein_input
- [ ] D3. Tạo topic inference_request
- [ ] D4. Tạo topic prediction_result
- [ ] D5. Tạo topic dead_letter
- [ ] D6. Viết producer config
- [ ] D7. Viết consumer config
- [ ] D8. Test throughput topic input

### Epic E - RabbitMQ control plane

- [ ] E1. Tạo exchange command_exchange
- [ ] E2. Tạo queue retry_inference
- [ ] E3. Tạo queue notification_queue
- [ ] E4. Tạo routing key convention
- [ ] E5. Viết retry consumer
- [ ] E6. Test ack/nack behavior

### Epic F - Cassandra foundation

- [ ] F1. Tạo keyspace protein_rt
- [ ] F2. Tạo bảng raw_protein_events
- [ ] F3. Tạo bảng request_status_by_id
- [ ] F4. Tạo bảng latest_prediction_by_protein
- [ ] F5. Tạo bảng prediction_history_by_protein
- [ ] F6. Tạo bảng failed_requests_by_time
- [ ] F7. Tạo bảng pipeline_metrics_by_window
- [ ] F8. Viết seed/test data script
- [ ] F9. Benchmark ghi 10k/100k rows
- [ ] F10. Benchmark query latest prediction

### Epic G - Spark streaming pipeline

- [ ] G1. Tạo Spark project skeleton
- [ ] G2. Đọc stream từ Kafka
- [ ] G3. Parse raw JSON
- [ ] G4. Validate required fields
- [ ] G5. Validate amino acid sequence
- [ ] G6. Deduplicate theo request_id
- [ ] G7. Ghi raw events vào Cassandra
- [ ] G8. Gọi feature builder
- [ ] G9. Gọi predictor
- [ ] G10. Post-process output
- [ ] G11. Ghi prediction vào Cassandra
- [ ] G12. Ghi status update vào Cassandra
- [ ] G13. Ghi metrics theo time window
- [ ] G14. Ghi lỗi vào DLQ

### Epic H - Inference package

- [ ] H1. Chuẩn hóa preprocess function
- [ ] H2. Chuẩn hóa feature function
- [ ] H3. Tải model artifact
- [ ] H4. Viết predict() interface
- [ ] H5. Viết postprocess() interface
- [ ] H6. Test với sample protein
- [ ] H7. Benchmark batch inference
- [ ] H8. Gắn model_version vào output

### Epic I - Serving API

- [ ] I1. API create inference request
- [ ] I2. API get request status
- [ ] I3. API get latest prediction
- [ ] I4. API get prediction history
- [ ] I5. API list failed requests
- [ ] I6. API retry request
- [ ] I7. API health check
- [ ] I8. API metrics endpoint

### Epic J - Monitoring & Ops

- [ ] J1. Dashboard Kafka lag
- [ ] J2. Dashboard Spark batch duration
- [ ] J3. Dashboard Cassandra write latency
- [ ] J4. Dashboard request status counts
- [ ] J5. Dashboard failed request trend
- [ ] J6. Alert node down Cassandra
- [ ] J7. Alert Kafka lag spike
- [ ] J8. Alert Spark job failure

### Epic K - QA & reliability

- [ ] K1. Test valid sequence flow
- [ ] K2. Test invalid sequence flow
- [ ] K3. Test duplicate request flow
- [ ] K4. Test DLQ flow
- [ ] K5. Test retry flow
- [ ] K6. Test Cassandra node failure
- [ ] K7. Test Spark restart recovery
- [ ] K8. Test replay idempotency

---

## 12. Ưu tiên triển khai theo thứ tự thực tế

### P0 - Phải có

- data profiling CAFA-6
- chọn solution competition
- canonical event schema
- Kafka + replay service
- Spark ingest + validate + write Cassandra
- Cassandra schema cho status/latest/history
- baseline inference chạy được

### P1 - Nên có

- RabbitMQ retry/control plane
- dashboard metrics
- API retry request
- benchmark Cassandra và Spark
- DLQ đầy đủ

### P2 - Nâng cao

- multi-model versioning
- explainability metadata
- autoscaling
- advanced alerting
- multi-datacenter deployment

---

## 13. Rủi ro kỹ thuật và cách giảm thiểu

### 13.1 Solution competition quá nặng cho realtime

**Rủi ro**

- inference latency cao

**Giảm thiểu**

- dùng micro-batch
- tách model serving service riêng
- cache model trong memory
- fallback baseline nhẹ hơn

### 13.2 Cassandra bị hotspot partition

**Rủi ro**

- write/read lệch node

**Giảm thiểu**

- thêm shard_id vào partition key
- chia bucket thời gian hợp lý
- benchmark từ sớm

### 13.3 Spark job khó recover khi schema thay đổi

**Rủi ro**

- pipeline lỗi khi event thay đổi

**Giảm thiểu**

- version hóa schema
- backward-compatible contract
- test schema registry nếu cần

### 13.4 Kafka backlog lớn

**Rủi ro**

- tăng end-to-end latency

**Giảm thiểu**

- scale consumer
- tăng partition hợp lý
- monitor lag liên tục

### 13.5 RabbitMQ bị dùng sai vai trò

**Rủi ro**

- biến RabbitMQ thành data backbone chính gây nghẽn

**Giảm thiểu**

- giữ Kafka cho data-plane throughput lớn
- giữ RabbitMQ cho command/retry/orchestration

---

## 14. Kiến nghị kỹ thuật quan trọng

1. **Không dùng RabbitMQ thay Kafka cho luồng dữ liệu chính**
2. **Không thiết kế Cassandra theo kiểu chuẩn hóa SQL**
3. **Không gắn chặt pipeline Spark với code notebook của solution competition**
4. **Phải version hóa model, feature, schema ngay từ đầu**
5. **Phải benchmark Cassandra trước khi chốt schema production**
6. **Phải có replay mechanism để test ổn định**

---

## 15. Đề xuất milestone quản lý

### Milestone 1

- hiểu dữ liệu
- chọn solution
- chốt architecture

### Milestone 2

- dựng streaming backbone
- dựng Cassandra schema
- ingest dữ liệu vào thành công

### Milestone 3

- inference realtime chạy được trên sample stream
- kết quả ghi được vào Cassandra

### Milestone 4

- có API/dashboard
- có metrics/alert cơ bản

### Milestone 5

- benchmark, test lỗi, demo end-to-end

---

## 16. Kết luận định hướng giao việc

Nếu mục tiêu là xây dựng **hệ thống Big Data realtime** cho dự đoán chức năng protein, thì trọng tâm kỹ thuật nên là:

1. **Kafka + Spark** cho ingestion và xử lý stream quy mô lớn
2. **RabbitMQ** cho điều phối retry/control events
3. **Cassandra** làm storage lõi cho serving, audit, metrics và prediction history

Điểm nổi bật nhất cần nhấn mạnh là:

- Cassandra rất hợp cho bài toán này vì dữ liệu mang tính **event-driven**, **append-heavy**, **time-series**, cần **scale ngang**, **độ sẵn sàng cao**, và **ghi liên tục**.
- Khi thiết kế đúng theo query pattern, Cassandra sẽ là nền tảng cực mạnh để phục vụ cả **realtime serving** lẫn **vận hành hệ thống**.

---

## 17. Gợi ý giao việc ngay trong sprint đầu tiên

### Sprint 1

- [ ] Data team: profiling CAFA-6 + chuẩn hóa event schema
- [ ] ML team: chọn 1 solution competition + chạy baseline offline
- [ ] Backend team: dựng skeleton API + request tracking
- [ ] Platform team: Docker Compose cho Kafka/RabbitMQ/Cassandra/Spark
- [ ] Data engineering: replay service phát stream từ CAFA-6
- [ ] Backend + data engineering: thiết kế Cassandra schema v1

### Sprint 2

- [ ] Spark đọc Kafka và validate event
- [ ] Ghi raw events và request status vào Cassandra
- [ ] Đóng gói inference module v1
- [ ] API lấy request status và latest prediction
- [ ] Dashboard throughput + error rate cơ bản
