# Architecture Notes

Ban dau du an duoc tach theo 3 luong lon:

1. Data plane: ingest -> Kafka -> Spark -> Cassandra
2. Control plane: RabbitMQ cho retry, orchestration, notification
3. Serving plane: API va dashboard doc tu Cassandra

Tai lieu nay la noi de bo sung architecture diagram, topic catalog va query patterns.
