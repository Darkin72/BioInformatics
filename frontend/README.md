# Dashboard frontend

Frontend là ứng dụng React + TypeScript + Vite cho hệ thống dự đoán chức năng protein theo thời gian thực.

## Chạy local

Từ thư mục `frontend`:

```powershell
npm install
npm run dev
```

Frontend gọi Serving API thật qua `VITE_API_BASE_URL`. Khi chạy local, cấu hình:

```powershell
$env:VITE_API_BASE_URL = "http://localhost:8001"
npm run dev
```

Nếu không cấu hình `VITE_API_BASE_URL`, frontend mặc định gọi `http://localhost:8001`.

## Build và lint

```powershell
npm run lint
npm run build
```

## Cấu hình chính

- `VITE_API_BASE_URL`: URL Serving API. Khi không có biến này, frontend mặc định gọi `http://localhost:8001`.
- Token đăng nhập được lưu trong `localStorage` với key `protein-function.access-token`.

## Màn hình hiện có

- Login
- Dashboard tổng quan
- Gửi protein request
- Trạng thái request
- Prediction mới nhất

Kế hoạch frontend chi tiết nằm trong [FE_task.md](FE_task.md).
