# Dashboard frontend

Frontend là ứng dụng React + TypeScript + Vite cho hệ thống dự đoán chức năng protein theo thời gian thực.

## Chạy local

Từ thư mục `frontend`:

```powershell
npm install
npm run dev
```

Frontend gọi Serving API qua `VITE_API_BASE_URL`. Khi chạy local, cấu hình:

```powershell
$env:VITE_API_BASE_URL = "http://localhost:8001"
npm run dev
```

Nếu không cấu hình `VITE_API_BASE_URL`, frontend mặc định gọi `http://localhost:8001`.

## Chạy cùng Kubernetes local

Mở frontend và API bằng port-forward:

```powershell
kubectl -n bioinformatics port-forward svc/frontend 5174:5173
kubectl -n bioinformatics port-forward svc/serving-api 8001:8000
kubectl -n bioinformatics port-forward svc/notification-service 8004:8003
```

Sau đó mở `http://localhost:5174`.

## Build và lint

```powershell
npm run lint
npm run build
```

## Cấu hình chính

- `VITE_API_BASE_URL`: URL Serving API. Khi không có biến này, frontend mặc định gọi `http://localhost:8001`.
- `VITE_EVENTS_BASE_URL`: URL Notification Service/SSE. Khi chạy Kubernetes local, thường là `http://localhost:8004` qua port-forward.
- Token đăng nhập được lưu trong `localStorage` với key `protein-function.access-token`.

## Màn hình hiện có

- Login.
- Dashboard tổng quan.
- Gửi protein request.
- Trạng thái request.
- Prediction mới nhất.

Kế hoạch frontend chi tiết nằm trong [FE_task.md](FE_task.md).
