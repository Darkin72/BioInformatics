# Job Spark Streaming

Thư mục này chứa pipeline Spark Structured Streaming đọc từ Kafka, xử lý event và ghi vào Cassandra.

Trạng thái hiện tại: khung giữ chỗ. Pipeline mục tiêu gồm parse JSON, validate protein sequence, chuẩn hóa metadata, gọi module inference và ghi request status/latest prediction/metrics vào Cassandra.
