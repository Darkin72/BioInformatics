# Notification service

Consumes Kafka events from the realtime pipeline, writes Cassandra serving tables, aggregates dashboard metrics, and streams UI updates over Server-Sent Events.

Main responsibilities:

- consume `request_status`, `prediction_result`, and `dead_letter`
- maintain Cassandra query tables for admin/dashboard views
- publish `/api/events/dashboard` SSE updates for browser consoles

