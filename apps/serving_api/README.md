# Serving API

Service tra cuu request status, latest prediction va prediction history tu Cassandra.

## Auth JWT

API hien co cac endpoint auth co ban:

- `POST /api/auth/login`: nhan `username`/`password`, tra JWT bearer token.
- `GET /api/auth/me`: kiem tra token hien tai.
- `POST /api/auth/logout`: revoke token hien tai trong phien chay API.

Role demo:

- `viewer/viewer123`: xem dashboard, request status va prediction.
- `operator/operator123`: quyen viewer va tao inference request.
- `admin/admin123`: toan quyen hien co.

Bien moi truong:

- `JWT_SECRET`: khoa ky JWT, can doi khi chay moi truong that.
- `JWT_EXPIRES_SECONDS`: thoi gian song token, mac dinh `3600`.
- `CORS_ALLOWED_ORIGINS`: danh sach origin frontend, phan cach bang dau phay.
