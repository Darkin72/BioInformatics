# Serving API

Service tra cứu request status, latest prediction và prediction history từ Cassandra.

## Endpoint

- `GET /health`
- `GET /v1/requests/{request_id}`
- `GET /v1/requests/{request_id}/prediction`
- `GET /v1/proteins/{protein_id}/latest`
- `GET /v1/proteins/{protein_id}/history?limit=20`
