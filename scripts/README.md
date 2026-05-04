# Scripts vận hành

Thư mục này chứa các script hỗ trợ phát triển, kiểm thử và vận hành local.

## Stress test gửi nhiều file sequence

Script [stress_submit_sequences.py](stress_submit_sequences.py) đọc nhiều file `.fa`, `.fasta`, `.faa`, `.fna` hoặc `.txt`, đăng nhập vào Serving API, rồi gửi đồng thời các sequence vào endpoint `/api/inference-requests`.

Tạo nhanh 20 file FASTA mẫu và gửi với 8 worker:

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences `
  --create-samples 20 `
  --workers 8
```

Chạy trên thư mục dữ liệu có sẵn:

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\data\stress_sequences `
  --workers 8 `
  --repeat 2 `
  --output stress-results.jsonl
```

Chỉ kiểm tra việc đọc file, không gọi API:

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\data\stress_sequences `
  --dry-run
```

Biến môi trường hỗ trợ:

- `API_BASE_URL`: URL Serving API, mặc định `http://localhost:8000`.
- `STRESS_USERNAME`: tài khoản có quyền `operator`, mặc định `operator`.
- `STRESS_PASSWORD`: mật khẩu, mặc định `operator123`.

Lưu ý: script gọi endpoint CAFA-6 thật thông qua Serving API, nên khi tăng `--workers`, `--repeat` hoặc số file đầu vào thì tải và chi phí phía endpoint thật cũng tăng theo.
