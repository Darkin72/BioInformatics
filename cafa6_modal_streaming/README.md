# CAFA-6 Modal Streaming Endpoint

Package này phục vụ ensemble CAFA-6 qua một Modal app riêng, có cả JSON API và SSE batch-streaming API.

Tài liệu đầy đủ:

```text
docs/cafa6_modal_streaming.md
```

Tài liệu API tập trung vào input/output:

```text
docs/cafa6_streaming_api_io.md
```

## Deploy

```bash
bash cafa6_modal_streaming/scripts/deploy.sh
```

## Gọi SSE endpoint

```bash
python cafa6_modal_streaming/scripts/call_streaming_endpoint.py \
  --url "$CAFA6_STREAM_PREDICT_SSE_URL" \
  --sequence MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV \
  --top-k 20 \
  --stream-batch-size 1
```
