# CAFA-6 Modal Streaming Endpoint

This package serves the CAFA-6 ensemble through a separate Modal app with both JSON and SSE batch-streaming APIs.

See the full documentation:

```text
docs/cafa6_modal_streaming.md
```

Input/output focused API documentation:

```text
docs/cafa6_streaming_api_io.md
```

Deploy:

```bash
bash cafa6_modal_streaming/scripts/deploy.sh
```

Call the SSE endpoint:

```bash
python cafa6_modal_streaming/scripts/call_streaming_endpoint.py \
  --url "$CAFA6_STREAM_PREDICT_SSE_URL" \
  --sequence MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV \
  --top-k 20 \
  --stream-batch-size 1
```
