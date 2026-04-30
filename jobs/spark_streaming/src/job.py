from __future__ import annotations

import json
import time
from typing import Any

import requests

from libs.protein_rt.cassandra_store import CassandraStore
from libs.protein_rt.config import CassandraConfig, KafkaConfig, ModalConfig
from libs.protein_rt.events import DeadLetterEvent, PredictionResultEvent, PredictionRow, RawProteinInputEvent
from libs.protein_rt.kafka_io import KafkaJsonProducer


def _spark_session():
    try:
        from pyspark.sql import SparkSession
    except ImportError as exc:
        raise RuntimeError("Install pyspark to run the streaming job") from exc

    return (
        SparkSession.builder.appName("protein-rt-cafa6-streaming")
        .config("spark.sql.shuffle.partitions", "8")
        .config(
            "spark.jars.packages",
            "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1",
        )
        .getOrCreate()
    )


def _parse_event(raw_value: str) -> RawProteinInputEvent:
    return RawProteinInputEvent.model_validate_json(raw_value)


def _event_top_k(event: RawProteinInputEvent, default_top_k: int) -> int:
    raw_top_k = event.metadata.get("top_k", default_top_k)
    try:
        top_k = int(raw_top_k)
    except (TypeError, ValueError):
        return default_top_k
    return min(max(top_k, 1), 500)


def _event_threshold(event: RawProteinInputEvent) -> float | None:
    raw_threshold = event.metadata.get("threshold")
    if raw_threshold is None:
        return None
    try:
        threshold = float(raw_threshold)
    except (TypeError, ValueError):
        return None
    return min(max(threshold, 0.0), 1.0)


def _call_modal(
    records: list[RawProteinInputEvent],
    modal_config: ModalConfig,
    top_k: int,
    threshold: float | None,
) -> tuple[dict[str, Any], int]:
    if not modal_config.predict_url:
        raise RuntimeError("CAFA6_PREDICT_URL is required for model inference")

    payload = {
        "records": [
            {"id": event.protein_id, "sequence": event.sequence}
            for event in records
        ],
        "top_k": top_k,
        "threshold": threshold,
        "include_branch_predictions": False,
    }
    started = time.perf_counter()
    response = requests.post(
        modal_config.predict_url,
        json=payload,
        timeout=modal_config.timeout_seconds,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    response.raise_for_status()
    return response.json(), elapsed_ms


def _result_events(
    request_events: list[RawProteinInputEvent],
    modal_response: dict[str, Any],
    latency_ms: int,
) -> list[PredictionResultEvent]:
    by_protein: dict[str, list[PredictionRow]] = {}
    for row in modal_response.get("predictions", []):
        prediction = PredictionRow.model_validate(row)
        by_protein.setdefault(prediction.protein_id, []).append(prediction)

    model = modal_response.get("model", {})
    model_name = model.get("name", "ensemble")
    threshold = model.get("threshold")

    results: list[PredictionResultEvent] = []
    for event in request_events:
        predictions = by_protein.get(event.protein_id, [])
        score_map = {item.go_term: float(item.score) for item in predictions}
        predicted_terms = list(score_map.keys())
        max_score = max(score_map.values()) if score_map else 0.0
        results.append(
            PredictionResultEvent(
                request_id=event.request_id,
                protein_id=event.protein_id,
                model_version=f"cafa6_modal_{model_name}",
                feature_version="sequence_v1",
                predicted_terms=predicted_terms,
                score_map=score_map,
                predictions=predictions,
                threshold_used=threshold,
                latency_ms=latency_ms,
                confidence_summary=f"top_terms={len(predicted_terms)};max_score={max_score:.6f}",
            )
        )
    return results


def _persist_batch(batch_df, batch_id: int) -> None:
    del batch_id
    values = [row.value for row in batch_df.selectExpr("CAST(value AS STRING) AS value").collect()]
    if not values:
        return

    store = CassandraStore(CassandraConfig())
    kafka_config = KafkaConfig()
    producer = KafkaJsonProducer(kafka_config.bootstrap_servers)
    modal_config = ModalConfig()
    try:
        valid_events: list[RawProteinInputEvent] = []
        for value in values:
            try:
                event = _parse_event(value)
                valid_events.append(event)
                store.put_request_status(
                    request_id=event.request_id,
                    protein_id=event.protein_id,
                    status="VALIDATED",
                    stage_name="spark_validation",
                )
            except Exception as exc:
                dead_letter = DeadLetterEvent(
                    request_id="unknown",
                    stage_name="spark_validation",
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                    payload={"raw_value": value},
                )
                store.put_failed_request(dead_letter)
                producer.send(
                    kafka_config.dead_letter_topic,
                    key=dead_letter.request_id,
                    value=dead_letter,
                )
                print(dead_letter.model_dump_json())

        grouped_events: dict[tuple[int, float | None], list[RawProteinInputEvent]] = {}
        for event in valid_events:
            group_key = (_event_top_k(event, modal_config.top_k), _event_threshold(event))
            grouped_events.setdefault(group_key, []).append(event)

        for (top_k, threshold), events in grouped_events.items():
            for offset in range(0, len(events), 64):
                chunk = events[offset : offset + 64]
                try:
                    modal_response, latency_ms = _call_modal(
                        chunk,
                        modal_config,
                        top_k,
                        threshold,
                    )
                    for result in _result_events(chunk, modal_response, latency_ms):
                        store.put_prediction(result)
                        producer.send(
                            kafka_config.prediction_topic,
                            key=result.protein_id,
                            value=result,
                        )
                        print(result.model_dump_json())
                except Exception as exc:
                    for event in chunk:
                        store.put_request_status(
                            request_id=event.request_id,
                            protein_id=event.protein_id,
                            status="FAILED",
                            stage_name="modal_inference",
                            error_code=type(exc).__name__,
                            error_message=str(exc),
                        )
                        dead_letter = DeadLetterEvent(
                            request_id=event.request_id,
                            protein_id=event.protein_id,
                            stage_name="modal_inference",
                            error_code=type(exc).__name__,
                            error_message=str(exc),
                            retryable=True,
                            payload=json.loads(event.model_dump_json()),
                        )
                        store.put_failed_request(dead_letter)
                        producer.send(
                            kafka_config.dead_letter_topic,
                            key=event.protein_id,
                            value=dead_letter,
                        )
                        print(dead_letter.model_dump_json())
    finally:
        producer.flush()
        store.close()


def run() -> None:
    kafka_config = KafkaConfig()
    spark = _spark_session()
    stream = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", kafka_config.bootstrap_servers)
        .option("subscribe", kafka_config.raw_topic)
        .option("startingOffsets", "latest")
        .load()
    )
    query = (
        stream.writeStream.foreachBatch(_persist_batch)
        .option("checkpointLocation", "/tmp/protein-rt/spark-checkpoints/cafa6")
        .trigger(processingTime="10 seconds")
        .start()
    )
    query.awaitTermination()


if __name__ == "__main__":
    run()
