# CAFA-6 Graph-Aware Modal Streaming Endpoint

Package này phục vụ artifact CAFA-6 graph-aware qua một Modal app riêng với một SSE API duy nhất. Request body chọn `ensemble`, `esm_mlp`, `protcnn` hoặc `bilstm`; stream phát cả event `progress` theo từng bước và kết quả `batch` cuối cùng.

Tài liệu đầy đủ:

```text
docs/cafa6_graph_aware_modal_streaming.md
```

Tài liệu API input/output:

```text
docs/cafa6_graph_aware_streaming_api_io.md
```

## Upload artifact

```bash
bash cafa6_graph_aware_modal_streaming/scripts/upload_artifacts.sh ./cafa6_graph_aware_artifacts
```

## Deploy

```bash
bash cafa6_graph_aware_modal_streaming/scripts/deploy.sh
```
