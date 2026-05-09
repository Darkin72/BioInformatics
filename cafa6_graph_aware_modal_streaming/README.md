# CAFA-6 Graph-Aware Modal Streaming Endpoint

This package serves the graph-aware CAFA-6 artifacts through a separate Modal app with a single SSE API. The request body chooses `ensemble`, `esm_mlp`, `protcnn`, or `bilstm`, and the stream emits both step-level `progress` events and final `batch` results.

See:

```text
docs/cafa6_graph_aware_modal_streaming.md
```

Input/output API reference:

```text
docs/cafa6_graph_aware_streaming_api_io.md
```

Upload artifacts:

```bash
bash cafa6_graph_aware_modal_streaming/scripts/upload_artifacts.sh ./cafa6_graph_aware_artifacts
```

Deploy:

```bash
bash cafa6_graph_aware_modal_streaming/scripts/deploy.sh
```
