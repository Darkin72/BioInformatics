from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

from cafa6_graph_aware_modal_streaming.models import (
    BiLSTMAttention,
    EmbeddingMLP,
    ProtCNN,
)


AA = "ACDEFGHIKLMNPQRSTVWY"
AA_TO_IDX = {aa: i + 1 for i, aa in enumerate(AA)}
PUBLIC_TO_BRANCH = {
    "bilstm": "bilstm_attention",
    "esm_mlp": "esm_mlp",
    "protcnn": "protcnn",
    "ensemble": "ensemble",
}
BRANCH_TO_PUBLIC = {value: key for key, value in PUBLIC_TO_BRANCH.items() if value != "ensemble"}


def clean_sequence(seq: str) -> str:
    seq = str(seq).strip().upper()
    return re.sub(r"\s+", "", seq)


def normalize_records(records: list[dict[str, Any]]) -> list[tuple[str, str]]:
    clean_records = []
    seen = set()
    for idx, item in enumerate(records):
        if not isinstance(item, dict):
            raise ValueError("Each record must be an object with id and sequence fields.")
        pid = str(item.get("id") or item.get("protein_id") or f"protein_{idx + 1}")
        seq = clean_sequence(item.get("sequence", ""))
        if not seq:
            continue
        base_id = pid
        if pid in seen:
            suffix = 2
            while f"{base_id}_{suffix}" in seen:
                suffix += 1
            pid = f"{base_id}_{suffix}"
        seen.add(pid)
        clean_records.append((pid, seq))
    if not clean_records:
        raise ValueError("No non-empty input sequences were provided.")
    return clean_records


def encode_sequence(seq: str, max_len: int) -> np.ndarray:
    arr = np.zeros(max_len, dtype=np.int64)
    for i, aa in enumerate(seq[:max_len]):
        arr[i] = AA_TO_IDX.get(aa, 0)
    return arr


def prepare_lm_sequences(batch_seqs: list[str], model_name: str) -> list[str]:
    if "prot_bert" in model_name.lower() or "protbert" in model_name.lower():
        cleaned = [re.sub(r"[UZOB]", "X", seq.upper()) for seq in batch_seqs]
        return [" ".join(list(seq)) for seq in cleaned]
    return [seq.upper() for seq in batch_seqs]


def pool_lm_outputs(outputs, attention_mask, pooling: str = "mean"):
    hidden = outputs.last_hidden_state
    mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
    if pooling == "cls":
        return hidden[:, 0]
    return (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1.0)


class CAFA6GraphAwareStreamingPredictor:
    def __init__(self, artifact_dir: str | Path, device: str | None = None):
        self.artifact_dir = Path(artifact_dir)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.cfg = json.loads((self.artifact_dir / "config.json").read_text())
        self.selected_terms = json.loads((self.artifact_dir / "go_terms.json").read_text())
        self.go_meta = json.loads((self.artifact_dir / "go_metadata.json").read_text())
        self.output_dim = len(self.selected_terms)

        self.model_states = self._load_branch_states()
        if not self.model_states:
            raise RuntimeError(f"No branch checkpoints found in {self.artifact_dir}")

        self.esm_tokenizer = None
        self.esm_model = None
        self.branch_models = {}
        self._load_runtime_models()

    def health(self) -> dict[str, Any]:
        available_public_models = sorted(
            [BRANCH_TO_PUBLIC[name] for name in self.branch_models] + ["ensemble"]
        )
        return {
            "status": "ok",
            "device": self.device,
            "artifact_dir": str(self.artifact_dir),
            "branches": sorted(self.branch_models),
            "supported_models": available_public_models,
            "num_go_terms": self.output_dim,
            "threshold": self.cfg.get("best_threshold_micro_f1"),
            "embedding_model_name": self.cfg.get("embedding_model_name"),
            "supports_batch_streaming": True,
        }

    def predict(
        self,
        records: list[dict[str, Any]],
        model_name: str = "ensemble",
        top_k: int = 100,
        threshold: float | None = None,
        include_branch_predictions: bool = False,
    ) -> dict[str, Any]:
        normalized = normalize_records(records)
        top_k = max(1, min(int(top_k), self.output_dim))
        return self._predict_normalized(
            normalized=normalized,
            requested_model=model_name,
            top_k=top_k,
            threshold=threshold,
            include_branch_predictions=include_branch_predictions,
        )

    def iter_predict_batches(
        self,
        records: list[dict[str, Any]],
        model_name: str = "ensemble",
        top_k: int = 100,
        threshold: float | None = None,
        include_branch_predictions: bool = False,
        stream_batch_size: int = 8,
    ) -> Iterator[dict[str, Any]]:
        normalized = normalize_records(records)
        top_k = max(1, min(int(top_k), self.output_dim))
        stream_batch_size = max(1, int(stream_batch_size))
        total_records = len(normalized)
        total_batches = math.ceil(total_records / stream_batch_size)

        for batch_index, start in enumerate(range(0, total_records, stream_batch_size)):
            batch = normalized[start : start + stream_batch_size]
            result = self._predict_normalized(
                normalized=batch,
                requested_model=model_name,
                top_k=top_k,
                threshold=threshold,
                include_branch_predictions=include_branch_predictions,
            )
            result.update(
                {
                    "batch_index": batch_index,
                    "batch_start": start,
                    "batch_size": len(batch),
                    "total_batches": total_batches,
                    "total_records": total_records,
                }
            )
            yield result

    def iter_predict_events(
        self,
        records: list[dict[str, Any]],
        model_name: str = "ensemble",
        top_k: int = 100,
        threshold: float | None = None,
        include_branch_predictions: bool = False,
        stream_batch_size: int = 8,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        normalized = normalize_records(records)
        top_k = max(1, min(int(top_k), self.output_dim))
        stream_batch_size = max(1, int(stream_batch_size))
        total_records = len(normalized)
        total_batches = math.ceil(total_records / stream_batch_size)

        yield (
            "progress",
            {
                "step": "normalize_input",
                "status": "done",
                "total_records": total_records,
                "total_batches": total_batches,
            },
        )

        for batch_index, start in enumerate(range(0, total_records, stream_batch_size)):
            batch = normalized[start : start + stream_batch_size]
            batch_meta = {
                "batch_index": batch_index,
                "batch_start": start,
                "batch_size": len(batch),
                "total_batches": total_batches,
                "total_records": total_records,
            }
            yield (
                "progress",
                {
                    **batch_meta,
                    "step": "batch_started",
                    "status": "running",
                    "model": model_name,
                },
            )
            yield from self._iter_predict_normalized_events(
                normalized=batch,
                requested_model=model_name,
                top_k=top_k,
                threshold=threshold,
                include_branch_predictions=include_branch_predictions,
                batch_meta=batch_meta,
            )

    def _predict_normalized(
        self,
        normalized: list[tuple[str, str]],
        requested_model: str,
        top_k: int,
        threshold: float | None,
        include_branch_predictions: bool,
    ) -> dict[str, Any]:
        requested_model = (requested_model or "ensemble").strip().lower()
        internal_model = self._resolve_requested_model(requested_model)
        branch_names = self._required_branch_names(internal_model, include_branch_predictions)
        branch_probs = self._compute_branch_probabilities(normalized, branch_names)
        return self._build_result(
            normalized=normalized,
            requested_model=requested_model,
            internal_model=internal_model,
            branch_probs=branch_probs,
            top_k=top_k,
            threshold=threshold,
            include_branch_predictions=include_branch_predictions,
        )

    def _iter_predict_normalized_events(
        self,
        normalized: list[tuple[str, str]],
        requested_model: str,
        top_k: int,
        threshold: float | None,
        include_branch_predictions: bool,
        batch_meta: dict[str, int],
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        requested_model = (requested_model or "ensemble").strip().lower()
        internal_model = self._resolve_requested_model(requested_model)
        branch_names = self._required_branch_names(internal_model, include_branch_predictions)
        progress_events: list[tuple[str, dict[str, Any]]] = []
        progress_callback = self._make_progress_callback(
            model_name=requested_model,
            batch_meta=batch_meta,
            sink=progress_events,
        )

        started_at = time.time()
        branch_probs = self._compute_branch_probabilities(
            normalized,
            branch_names,
            progress_callback=progress_callback,
        )
        if internal_model == "ensemble":
            progress_callback(
                "combine_ensemble",
                "running",
                source_branches=sorted(BRANCH_TO_PUBLIC.get(name, name) for name in branch_probs),
            )
        result = self._build_result(
            normalized=normalized,
            requested_model=requested_model,
            internal_model=internal_model,
            branch_probs=branch_probs,
            top_k=top_k,
            threshold=threshold,
            include_branch_predictions=include_branch_predictions,
        )
        if internal_model == "ensemble":
            progress_callback(
                "combine_ensemble",
                "done",
                combined_branches=sorted(BRANCH_TO_PUBLIC.get(name, name) for name in branch_probs),
            )
        progress_callback(
            "postprocess_predictions",
            "done",
            elapsed_seconds=round(time.time() - started_at, 3),
            prediction_rows=len(result["predictions"]),
        )
        yield from progress_events
        yield ("batch", {**result, **batch_meta})

    def _required_branch_names(
        self,
        internal_model: str,
        include_branch_predictions: bool,
    ) -> list[str]:
        if internal_model == "ensemble" or include_branch_predictions:
            return sorted(self.branch_models)
        return [internal_model]

    def _make_progress_callback(
        self,
        model_name: str,
        batch_meta: dict[str, int],
        sink: list[tuple[str, dict[str, Any]]],
    ):
        def callback(step: str, status: str, **extra: Any) -> None:
            payload = {
                **batch_meta,
                "model": model_name,
                "step": step,
                "status": status,
            }
            payload.update(extra)
            sink.append(("progress", payload))

        return callback

    def _build_result(
        self,
        normalized: list[tuple[str, str]],
        requested_model: str,
        internal_model: str,
        branch_probs: dict[str, np.ndarray],
        top_k: int,
        threshold: float | None,
        include_branch_predictions: bool,
    ) -> dict[str, Any]:
        if internal_model == "ensemble":
            weights = self._ensemble_weights(branch_probs)
            probs = sum(weights[name] * branch_probs[name] for name in weights).astype(np.float32)
            model_info = {
                "name": "ensemble",
                "branches": sorted(BRANCH_TO_PUBLIC.get(name, name) for name in branch_probs),
                "weights": {BRANCH_TO_PUBLIC.get(name, name): value for name, value in weights.items()},
                "threshold": self._resolve_threshold(threshold),
                "top_k": top_k,
            }
        else:
            probs = branch_probs[internal_model]
            model_info = {
                "name": requested_model,
                "resolved_branch": internal_model,
                "threshold": self._resolve_threshold(threshold),
                "top_k": top_k,
            }

        result = {
            "predictions": self._prediction_rows(normalized, probs, requested_model, top_k, threshold),
            "records": [
                {"protein_id": pid, "length": len(seq), "sequence_preview": seq[:60]}
                for pid, seq in normalized
            ],
            "model": model_info,
        }
        if internal_model == "ensemble" and include_branch_predictions:
            result["branch_predictions"] = {
                BRANCH_TO_PUBLIC.get(name, name): self._prediction_rows(
                    normalized,
                    probs,
                    BRANCH_TO_PUBLIC.get(name, name),
                    top_k,
                    threshold,
                )
                for name, probs in branch_probs.items()
            }
        return result

    def _resolve_requested_model(self, model_name: str) -> str:
        if model_name not in PUBLIC_TO_BRANCH:
            raise ValueError(
                "Unsupported model. Use one of: ensemble, esm_mlp, protcnn, bilstm."
            )
        internal_model = PUBLIC_TO_BRANCH[model_name]
        if internal_model == "ensemble":
            if not self.branch_models:
                raise RuntimeError("No branch models are available for ensemble inference.")
            return internal_model
        if internal_model not in self.branch_models:
            raise ValueError(f"Model '{model_name}' is not available in loaded artifacts.")
        return internal_model

    def _compute_branch_probabilities(
        self,
        normalized: list[tuple[str, str]],
        branch_names: list[str],
        progress_callback=None,
    ) -> dict[str, np.ndarray]:
        branch_probs = {}

        if "esm_mlp" in branch_names:
            if progress_callback is not None:
                progress_callback("extract_esm_embeddings", "running")
            x_esm = self._extract_esm_embeddings(normalized)
            if progress_callback is not None:
                progress_callback(
                    "extract_esm_embeddings",
                    "done",
                    embedding_rows=len(normalized),
                    embedding_dim=int(x_esm.shape[1]),
                )
            if progress_callback is not None:
                progress_callback("run_esm_mlp", "running")
            branch_probs["esm_mlp"] = self._predict_numpy(
                self.branch_models["esm_mlp"],
                x_esm,
                int(self.cfg.get("esm_batch_size", 512)),
            )
            if progress_callback is not None:
                progress_callback("run_esm_mlp", "done")

        needs_sequence_tensor = any(branch in branch_names for branch in ("protcnn", "bilstm_attention"))
        x_seq = None
        if needs_sequence_tensor:
            if progress_callback is not None:
                progress_callback("encode_sequence_tensor", "running")
            x_seq = np.vstack(
                [
                    encode_sequence(seq, int(self.cfg["sequence_max_length"]))
                    for _, seq in normalized
                ]
            )
            if progress_callback is not None:
                progress_callback(
                    "encode_sequence_tensor",
                    "done",
                    tensor_shape=list(x_seq.shape),
                )

        if "protcnn" in branch_names:
            if progress_callback is not None:
                progress_callback("run_protcnn", "running")
            branch_probs["protcnn"] = self._predict_numpy(
                self.branch_models["protcnn"],
                x_seq,
                int(self.cfg.get("sequence_batch_size", 256)),
            )
            if progress_callback is not None:
                progress_callback("run_protcnn", "done")

        if "bilstm_attention" in branch_names:
            batch_size = max(32, int(self.cfg.get("sequence_batch_size", 256)) // 4)
            if progress_callback is not None:
                progress_callback("run_bilstm", "running")
            branch_probs["bilstm_attention"] = self._predict_numpy(
                self.branch_models["bilstm_attention"], x_seq, batch_size
            )
            if progress_callback is not None:
                progress_callback("run_bilstm", "done")

        if len(branch_names) == 1 and progress_callback is not None:
            progress_callback(
                "select_model_output",
                "done",
                selected_branches=sorted(BRANCH_TO_PUBLIC.get(name, name) for name in branch_probs),
            )

        return branch_probs

    def _load_branch_states(self):
        states = {}
        ckpt_dir = self.artifact_dir / "branch_checkpoints"
        if ckpt_dir.exists():
            for path in sorted(ckpt_dir.glob("*.pt")):
                obj = torch.load(path, map_location="cpu")
                branch = obj.get("branch", path.stem) if isinstance(obj, dict) else path.stem
                states[branch] = obj.get("state_dict", obj) if isinstance(obj, dict) else obj

        for full_name in ("graph_aware_models.pt", "cafa6_high_performance_models.pt"):
            full_ckpt = self.artifact_dir / full_name
            if full_ckpt.exists() and not {"esm_mlp", "protcnn", "bilstm_attention"}.issubset(states):
                obj = torch.load(full_ckpt, map_location="cpu")
                for branch, state in obj.get("model_states", {}).items():
                    states.setdefault(branch, state)
        return states

    def _load_runtime_models(self):
        if "esm_mlp" in self.model_states:
            from transformers import AutoModel, AutoTokenizer

            model_name = self.cfg["embedding_model_name"]
            self.esm_tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.esm_model = AutoModel.from_pretrained(model_name).to(self.device).eval()
            if self.device == "cuda" and self.cfg.get("use_fp16_embeddings", True):
                self.esm_model.half()

            state = self.model_states["esm_mlp"]
            first_weight = next(v for k, v in state.items() if k.endswith("weight") and v.ndim == 2)
            input_dim = int(first_weight.shape[1])
            model = EmbeddingMLP(
                input_dim,
                self.output_dim,
                self.cfg["esm_hidden_dims"],
                self.cfg["esm_dropout"],
            )
            model.load_state_dict(state)
            self.branch_models["esm_mlp"] = model.to(self.device).eval()

        if "protcnn" in self.model_states:
            model = ProtCNN(self.output_dim, dropout=self.cfg["protcnn_dropout"])
            model.load_state_dict(self.model_states["protcnn"])
            self.branch_models["protcnn"] = model.to(self.device).eval()

        if "bilstm_attention" in self.model_states:
            model = BiLSTMAttention(self.output_dim, dropout=self.cfg["bilstm_dropout"])
            model.load_state_dict(self.model_states["bilstm_attention"])
            self.branch_models["bilstm_attention"] = model.to(self.device).eval()

    @torch.no_grad()
    def _extract_esm_embeddings(self, records: list[tuple[str, str]]) -> np.ndarray:
        if self.esm_model is None or self.esm_tokenizer is None:
            return None

        batch_size = int(self.cfg.get("embedding_batch_size", 8))
        max_length = int(self.cfg["embedding_max_length"])
        model_name = self.cfg["embedding_model_name"]
        vectors = []
        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            seqs = [seq[:max_length] for _, seq in batch]
            seqs = prepare_lm_sequences(seqs, model_name)
            toks = self.esm_tokenizer(
                seqs,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=max_length,
            )
            toks = {k: v.to(self.device) for k, v in toks.items()}
            if self.device == "cuda":
                with torch.autocast(
                    device_type="cuda", enabled=bool(self.cfg.get("use_fp16_embeddings", True))
                ):
                    pooled = pool_lm_outputs(
                        self.esm_model(**toks),
                        toks["attention_mask"],
                        self.cfg.get("embedding_pooling", "mean"),
                    )
            else:
                pooled = pool_lm_outputs(
                    self.esm_model(**toks),
                    toks["attention_mask"],
                    self.cfg.get("embedding_pooling", "mean"),
                )
            vectors.append(pooled.float().cpu().numpy())
        return np.vstack(vectors).astype(np.float32)

    @torch.no_grad()
    def _predict_numpy(self, model, x: np.ndarray, batch_size: int) -> np.ndarray:
        loader = DataLoader(
            TensorDataset(torch.from_numpy(x)),
            batch_size=batch_size,
            shuffle=False,
            num_workers=0,
        )
        chunks = []
        for (xb,) in loader:
            xb = xb.to(self.device)
            chunks.append(torch.sigmoid(model(xb)).cpu().numpy().astype(np.float32))
        return np.vstack(chunks)

    def _ensemble_weights(self, branch_probs: dict[str, np.ndarray]) -> dict[str, float]:
        raw_weights = self.cfg.get("active_ensemble_weights") or {
            k: self.cfg["ensemble_weights"].get(k, 1.0) for k in branch_probs
        }
        weights = {k: float(raw_weights.get(k, 0.0)) for k in branch_probs}
        weight_sum = sum(weights.values())
        if weight_sum <= 0:
            weights = {k: 1.0 for k in branch_probs}
            weight_sum = sum(weights.values())
        return {k: v / weight_sum for k, v in weights.items()}

    def _resolve_threshold(self, threshold: float | None) -> float:
        if threshold is None:
            return float(self.cfg.get("best_threshold_micro_f1", 0.0))
        return float(threshold)

    def _prediction_rows(
        self,
        records: list[tuple[str, str]],
        probs: np.ndarray,
        model_name: str,
        top_k: int,
        threshold: float | None,
    ) -> list[dict[str, Any]]:
        rows = []
        threshold_value = self._resolve_threshold(threshold)
        term_to_aspect = self.go_meta.get("term_to_aspect", {})
        term_name = self.go_meta.get("term_name", {})
        for i, (pid, _) in enumerate(records):
            order = np.argsort(-probs[i])[:top_k]
            for j in order:
                score = float(probs[i, j])
                if score < threshold_value:
                    continue
                term = self.selected_terms[j]
                rows.append(
                    {
                        "model": model_name,
                        "protein_id": pid,
                        "go_term": term,
                        "score": round(score, 6),
                        "aspect": term_to_aspect.get(term),
                        "name": term_name.get(term, ""),
                    }
                )
        return rows
