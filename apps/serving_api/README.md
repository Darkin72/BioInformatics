# Serving API

Service này phục vụ tra cứu request status, latest prediction và prediction history từ Cassandra. Nó cũng xử lý JWT auth, tài khoản admin và các endpoint dashboard.

Trong giai đoạn hiện tại, phần phân tích thật chạy ở CAFA-6 Modal endpoint nằm ngoài repo này. Endpoint `POST /api/inference-requests` gọi URL cấu hình qua `CAFA6_PREDICT_URL`, gửi sequence thật của user và map response `predictions` về latest prediction của hệ thống.

## Xác thực JWT

API hiện có các endpoint xác thực cơ bản:

- `POST /api/auth/login`: nhận `username`/`password`, trả JWT bearer token.
- `GET /api/auth/me`: kiểm tra token hiện tại.
- `POST /api/auth/logout`: revoke token hiện tại trong phiên chạy API.

Role demo:

- `viewer/viewer123`: xem dashboard, request status và prediction.
- `operator/operator123`: có quyền viewer và tạo inference request.
- `admin/admin123`: toàn quyền hiện có.

## Biến môi trường

- `JWT_SECRET`: khóa ký JWT, cần đổi khi chạy môi trường thật.
- `JWT_EXPIRES_SECONDS`: thời gian sống token, mặc định `3600`.
- `CORS_ALLOWED_ORIGINS`: danh sách origin frontend, phân cách bằng dấu phẩy.
- `CAFA6_PREDICT_URL`: URL endpoint `cafa6-predict`, bắt buộc để chạy inference thật.
- `CAFA6_HEALTH_URL`: URL endpoint `cafa6-health`, dùng để kiểm tra Modal service.
- `CAFA6_TOP_K`: số GO term tối đa lấy từ endpoint, mặc định `20`.
- `CAFA6_TIMEOUT_SECONDS`: timeout khi gọi endpoint, mặc định `60`.

## CAFA-6 Modal client

- File chính: `apps/serving_api/src/cafa6_client.py`.
- Request gửi tới Modal theo contract trong `api/README.md`: `records`, `top_k`, `threshold`, `include_branch_predictions`.
- Response được map từ `go_term`, `name`, `aspect`, `score` sang `PredictionTerm`.
- Nếu `CAFA6_PREDICT_URL` chưa được cấu hình hoặc endpoint lỗi, request inference được ghi trạng thái `failed` với `error_code=ANALYSIS_API_ERROR`.
