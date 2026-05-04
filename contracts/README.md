# Data contract

Thư mục này lưu event schema và tài liệu contract giữa producer-consumer.

Các schema hiện có:

- `schemas/raw_input_event.json`: contract cho event protein đầu vào.
- `schemas/prediction_result_event.json`: contract cho event kết quả dự đoán.

Mọi producer và consumer nên validate payload theo schema tương ứng trước khi ghi hoặc đọc từ streaming backbone.
