# Frontend Task Plan

## 1. Mục tiêu frontend

Xây dựng giao diện web cho hệ thống dự đoán chức năng protein theo thời gian thực, tập trung vào:

- Gửi protein sequence để tạo yêu cầu inference.
- Theo dõi trạng thái xử lý của request.
- Xem kết quả dự đoán mới nhất theo protein.
- Xem lịch sử prediction theo thời gian.
- Quan sát vận hành pipeline: throughput, latency, error rate, request status.
- Hỗ trợ operator xem request lỗi và retry khi cần.

Frontend hiện là project **React + TypeScript + Vite** trong thư mục `frontend`.

---

## 2. Phạm vi giai đoạn đầu

### Cần làm

1. Dashboard tổng quan vận hành realtime.
2. Màn hình submit protein sequence.
3. Màn hình tra cứu request status.
4. Màn hình latest prediction theo `protein_id`.
5. Màn hình prediction history theo `protein_id`.
6. Màn hình failed requests và thao tác retry.
7. Tầng gọi API backend có error/loading state rõ ràng.
8. Component dùng lại cho bảng, form, trạng thái, biểu đồ cơ bản.

### Chưa cần làm ở giai đoạn đầu

1. Auth phức tạp nhiều role nếu backend chưa có.
2. Realtime WebSocket/SSE bắt buộc; có thể dùng polling trước.
3. Visualize ontology GO term dạng graph lớn.
4. Upload batch file lớn.
5. Quản trị Kafka/RabbitMQ/Cassandra trực tiếp từ UI.

---

## 3. Tech stack đề xuất

### Đang có

- React
- TypeScript
- Vite
- ESLint

### Nên bổ sung khi bắt đầu triển khai UI thật

- `react-router-dom` cho routing.
- `@tanstack/react-query` cho API cache/loading/error/refetch.
- `recharts` hoặc `echarts-for-react` cho chart.
- `lucide-react` cho icon.
- Một thư viện UI nhẹ hoặc tự xây component nội bộ nếu scope nhỏ.

Không nên thêm quá nhiều framework UI nặng trước khi chốt thiết kế màn hình.

---

## 4. Route và màn hình cần có

### 4.1 `/`

Tên màn hình: **Overview Dashboard**

Mục tiêu:

- Cho operator nhìn nhanh tình trạng hệ thống.
- Hiển thị các chỉ số chính theo thời gian gần nhất.

Nội dung:

- Tổng số request hôm nay.
- Số request `pending`, `processing`, `completed`, `failed`.
- Throughput theo phút/giờ.
- Latency trung bình/p95 theo stage.
- Error rate.
- Recent predictions.
- Recent failed requests.

Task:

- [ ] Tạo layout dashboard chính.
- [ ] Tạo metric cards.
- [ ] Tạo line chart throughput.
- [ ] Tạo chart latency theo stage.
- [ ] Tạo bảng recent predictions.
- [ ] Tạo bảng recent failed requests.
- [ ] Thêm auto refresh hoặc nút refresh thủ công.

Acceptance criteria:

- Dashboard đọc được dữ liệu từ API hoặc mock service.
- Loading, empty, error state không làm vỡ layout.
- Số liệu có timestamp cập nhật cuối cùng.

---

### 4.2 `/submit`

Tên màn hình: **Submit Protein**

Mục tiêu:

- Cho người dùng gửi protein sequence để tạo inference request.

Form field:

- `protein_id`
- `sequence`
- `source`
- `metadata` dạng JSON optional

Validation frontend:

- `protein_id` bắt buộc.
- `sequence` bắt buộc.
- Chỉ cho phép ký tự amino acid hợp lệ: `ACDEFGHIKLMNPQRSTVWY`.
- Cảnh báo nếu sequence quá ngắn hoặc quá dài.
- Metadata JSON phải parse được nếu nhập.

Task:

- [ ] Tạo form submit protein.
- [ ] Validate sequence ngay trên client.
- [ ] Gọi API tạo request.
- [ ] Hiển thị `request_id` sau khi submit thành công.
- [ ] Có link chuyển sang trang request status.

Acceptance criteria:

- Không gửi request nếu input sai format.
- Submit thành công hiển thị request id rõ ràng.
- Lỗi backend hiển thị message dễ hiểu.

---

### 4.3 `/requests/:requestId`

Tên màn hình: **Request Status**

Mục tiêu:

- Theo dõi trạng thái xử lý của một request.

Nội dung:

- `request_id`
- `protein_id`
- `current_status`
- `stage_name`
- `created_at`
- `updated_at`
- `model_version`
- `feature_version`
- `retry_count`
- `error_code`
- `error_message`
- Timeline trạng thái nếu backend hỗ trợ.

Task:

- [ ] Tạo page request detail.
- [ ] Gọi API lấy trạng thái request.
- [ ] Hiển thị status badge thống nhất.
- [ ] Thêm polling khi request chưa hoàn tất.
- [ ] Thêm nút retry nếu request failed và backend cho phép.

Acceptance criteria:

- Status đang xử lý tự cập nhật theo chu kỳ cấu hình được.
- Request failed hiển thị lý do lỗi và thao tác retry.

---

### 4.4 `/proteins/:proteinId/latest`

Tên màn hình: **Latest Prediction**

Mục tiêu:

- Xem kết quả dự đoán mới nhất của một protein.

Nội dung:

- `protein_id`
- `request_id`
- `predicted_at`
- `model_version`
- `confidence_summary`
- Danh sách top GO terms và score.
- Link sang prediction history.

Task:

- [ ] Tạo ô search protein id.
- [ ] Tạo page latest prediction.
- [ ] Hiển thị top terms dạng bảng.
- [ ] Format score thống nhất.
- [ ] Hiển thị empty state nếu chưa có prediction.

Acceptance criteria:

- Tra cứu protein id trực tiếp được.
- Top terms dễ scan, có sort theo score giảm dần.

---

### 4.5 `/proteins/:proteinId/history`

Tên màn hình: **Prediction History**

Mục tiêu:

- Xem lịch sử dự đoán của một protein theo thời gian.

Filter:

- `from`
- `to`
- `model_version` optional

Nội dung:

- Bảng prediction history.
- Biểu đồ thay đổi confidence/score theo thời gian nếu dữ liệu phù hợp.
- Detail panel cho từng prediction.

Task:

- [ ] Tạo filter date range.
- [ ] Gọi API history.
- [ ] Tạo bảng history.
- [ ] Cho phép mở chi tiết một prediction.
- [ ] Thêm phân trang hoặc infinite load nếu dữ liệu lớn.

Acceptance criteria:

- Filter date range hoạt động.
- Không render danh sách quá dài gây chậm UI.

---

### 4.6 `/failed-requests`

Tên màn hình: **Failed Requests**

Mục tiêu:

- Cho operator xem request lỗi và retry.

Filter:

- Date/time bucket.
- `status_code`
- `stage_name`
- `retryable`

Nội dung:

- Bảng request lỗi.
- Lý do lỗi.
- Retry action.
- Link sang request detail.

Task:

- [ ] Tạo bảng failed requests.
- [ ] Tạo filter theo ngày/trạng thái/stage.
- [ ] Gọi API retry request.
- [ ] Thêm confirm trước khi retry.
- [ ] Update lại bảng sau retry.

Acceptance criteria:

- Chỉ hiện retry action khi request retryable.
- Retry thành công có feedback rõ ràng.

---

## 5. API contract frontend cần backend cung cấp

Tên endpoint có thể thay đổi, nhưng frontend cần các khả năng sau.

### Create inference request

```http
POST /api/inference-requests
```

Request:

```json
{
  "protein_id": "P12345",
  "sequence": "MENDELACDEFGHIK",
  "source": "manual_ui",
  "metadata": {
    "species": "optional"
  }
}
```

Response:

```json
{
  "request_id": "uuid",
  "protein_id": "P12345",
  "current_status": "pending",
  "created_at": "2026-04-27T10:00:00Z"
}
```

### Get request status

```http
GET /api/inference-requests/{request_id}
```

### Get latest prediction

```http
GET /api/proteins/{protein_id}/latest-prediction
```

### Get prediction history

```http
GET /api/proteins/{protein_id}/prediction-history?from=2026-04-01T00:00:00Z&to=2026-04-27T23:59:59Z
```

### List failed requests

```http
GET /api/failed-requests?date=2026-04-27&status_code=VALIDATION_ERROR
```

### Retry request

```http
POST /api/inference-requests/{request_id}/retry
```

### Get pipeline metrics

```http
GET /api/metrics/pipeline?from=2026-04-27T00:00:00Z&to=2026-04-27T23:59:59Z&window=minute
```

---

## 6. Data model TypeScript đề xuất

```ts
export type RequestStatus =
  | 'pending'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'retrying'
  | 'cancelled'

export interface InferenceRequest {
  request_id: string
  protein_id: string
  created_at: string
  updated_at?: string
  current_status: RequestStatus
  stage_name?: string
  error_code?: string
  error_message?: string
  retry_count?: number
  model_version?: string
  feature_version?: string
}

export interface PredictionTerm {
  term_id: string
  term_name?: string
  ontology?: 'BP' | 'MF' | 'CC'
  score: number
}

export interface LatestPrediction {
  protein_id: string
  request_id: string
  predicted_at: string
  model_version: string
  top_terms: PredictionTerm[]
  confidence_summary?: string
}

export interface PipelineMetricPoint {
  window_start: string
  window_end: string
  metric_name: string
  metric_value: number
  tags?: Record<string, string>
}
```

---

## 7. Cấu trúc thư mục frontend đề xuất

```text
frontend/src
  app/
    routes.tsx
    queryClient.ts
  components/
    StatusBadge.tsx
    MetricCard.tsx
    DataTable.tsx
    EmptyState.tsx
    ErrorState.tsx
    LoadingState.tsx
  features/
    dashboard/
      DashboardPage.tsx
      dashboardApi.ts
    submitProtein/
      SubmitProteinPage.tsx
      proteinValidation.ts
    requests/
      RequestStatusPage.tsx
      requestsApi.ts
    predictions/
      LatestPredictionPage.tsx
      PredictionHistoryPage.tsx
      predictionsApi.ts
    failedRequests/
      FailedRequestsPage.tsx
      failedRequestsApi.ts
  shared/
    apiClient.ts
    types.ts
    date.ts
    format.ts
```

Nguyên tắc:

- Mỗi feature tự giữ page, API wrapper và helper riêng.
- Type dùng chung đặt ở `shared/types.ts`.
- Không gọi `fetch` trực tiếp rải rác trong component; đi qua API wrapper.
- Component phải có loading, empty và error state.

---

## 8. UI/UX guideline

- Giao diện nên là operational dashboard, ưu tiên dễ đọc và thao tác nhanh.
- Không làm landing page marketing.
- Navigation trái hoặc top bar đơn giản:
  - Overview
  - Submit
  - Requests
  - Predictions
  - Failed Requests
- Status dùng màu nhất quán:
  - `pending`: xám
  - `processing`: xanh dương
  - `completed`: xanh lá
  - `failed`: đỏ
  - `retrying`: vàng/cam
- Bảng phải có trạng thái loading/empty/error.
- Form phải validate trước khi gọi API.
- Text kỹ thuật như `request_id`, `protein_id`, `model_version` dùng monospace.
- Timestamp hiển thị local time, nhưng giữ ISO UTC trong payload.

---

## 9. Thứ tự ưu tiên triển khai

### P0 - Bắt buộc cho demo đầu tiên

- [ ] Setup routing.
- [ ] Tạo layout app chính.
- [ ] Tạo API client.
- [ ] Tạo mock API hoặc cấu hình API base URL.
- [ ] Màn hình submit protein.
- [ ] Màn hình request status.
- [ ] Màn hình latest prediction.
- [ ] Dashboard metric cards cơ bản.

### P1 - Nên có

- [ ] Prediction history.
- [ ] Failed requests.
- [ ] Retry request.
- [ ] Throughput/latency/error chart.
- [ ] Auto refresh dashboard.
- [ ] Search nhanh theo `request_id` và `protein_id`.

### P2 - Nâng cao

- [ ] Realtime update bằng WebSocket/SSE.
- [ ] Export CSV cho prediction history.
- [ ] So sánh prediction giữa nhiều model version.
- [ ] Role-based UI.
- [ ] Audit log UI cho thao tác retry.

---

## 10. Sprint đề xuất

### Sprint FE 1

- [ ] Dọn template Vite mặc định.
- [ ] Tạo app shell và navigation.
- [ ] Tạo API client dùng `VITE_API_BASE_URL`.
- [ ] Tạo mock data để phát triển độc lập backend.
- [ ] Làm Submit Protein page.
- [ ] Làm Request Status page.

Deliverable:

- Người dùng submit sequence mock được.
- Người dùng xem trạng thái request mock được.

### Sprint FE 2

- [ ] Làm Latest Prediction page.
- [ ] Làm Prediction History page.
- [ ] Làm Dashboard overview.
- [ ] Tích hợp chart cơ bản.
- [ ] Chuẩn hóa status badge, table, loading/error state.

Deliverable:

- Có UI demo luồng submit -> status -> latest prediction.
- Có dashboard chỉ số cơ bản.

### Sprint FE 3

- [ ] Làm Failed Requests page.
- [ ] Làm retry action.
- [ ] Kết nối API backend thật.
- [ ] Xử lý lỗi API thống nhất.
- [ ] Chạy build/lint.

Deliverable:

- FE kết nối backend thật.
- Operator xem lỗi và retry được.

---

## 11. Definition of Done

Một task frontend được xem là xong khi:

- Có UI hoàn chỉnh cho happy path.
- Có loading state.
- Có empty state.
- Có error state.
- Có validate input nếu là form.
- Có type TypeScript rõ ràng.
- Không có lỗi lint/build.
- Component responsive ở desktop và tablet.
- Tên field khớp với API contract đã thống nhất.

---

## 12. Rủi ro và lưu ý

- Backend API chưa chốt thì FE nên có mock layer để không bị chặn.
- Dataset và prediction term có thể lớn, tránh render toàn bộ danh sách một lần.
- Polling quá dày có thể tạo tải không cần thiết; mặc định 5-10 giây cho request đang xử lý là đủ.
- Cần thống nhất format status từ backend sớm để UI không phải mapping quá nhiều.
- Cần thống nhất format GO term: `term_id`, `term_name`, `ontology`, `score`.

