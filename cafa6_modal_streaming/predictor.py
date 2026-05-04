from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

from cafa6_modal_streaming.models import BiLSTMAttention, EmbeddingMLP, ProtCNN


AA = "ACDEFGHIKLMNPQRSTVWY"
AA_TO_IDX = {aa: i + 1 for i, aa in enumerate(AA)}


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


class CAFA6StreamingPredictor:
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
        return {
            "status": "ok",
            "device": self.device,
            "artifact_dir": str(self.artifact_dir),
            "branches": sorted(self.branch_models),
            "num_go_terms": self.output_dim,
            "threshold": self.cfg.get("best_threshold_micro_f1"),
            "embedding_model_name": self.cfg.get("embedding_model_name"),
            "supports_batch_streaming": True,
        }

    def predict(
        self,
        records: list[dict[str, Any]],
        top_k: int = 100,
        threshold: float | None = None,
        include_branch_predictions: bool = False,
    ) -> dict[str, Any]:
        normalized = normalize_records(records)
        top_k = max(1, min(int(top_k), self.output_dim))
        return self._predict_normalized(
            normalized=normalized,
            top_k=top_k,
            threshold=threshold,
            include_branch_predictions=include_branch_predictions,
        )

    def iter_predict_batches(
        self,
        records: list[dict[str, Any]],
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

    def _predict_normalized(
        self,
        normalized: list[tuple[str, str]],
        top_k: int,
        threshold: float | None,
        include_branch_predictions: bool,
    ) -> dict[str, Any]:
        branch_probs = {}
        if "esm_mlp" in self.branch_models:
            x_esm = self._extract_esm_embeddings(normalized)
            branch_probs["esm_mlp"] = self._predict_numpy(
                self.branch_models["esm_mlp"],
                x_esm,
                int(self.cfg.get("esm_batch_size", 512)),
            )

        needs_sequence_tensor = any(
            branch in self.branch_models for branch in ("protcnn", "bilstm_attention")
        )
        x_seq = None
        if needs_sequence_tensor:
            x_seq = np.vstack(
                [
                    encode_sequence(seq, int(self.cfg["sequence_max_length"]))
                    for _, seq in normalized
                ]
            )

        if "protcnn" in self.branch_models:
            branch_probs["protcnn"] = self._predict_numpy(
                self.branch_models["protcnn"],
                x_seq,
                int(self.cfg.get("sequence_batch_size", 256)),
            )

        if "bilstm_attention" in self.branch_models:
            batch_size = max(32, int(self.cfg.get("sequence_batch_size", 256)) // 4)
            branch_probs["bilstm_attention"] = self._predict_numpy(
                self.branch_models["bilstm_attention"], x_seq, batch_size
            )

        weights = self._ensemble_weights(branch_probs)
        ensemble_probs = sum(weights[name] * branch_probs[name] for name in weights).astype(
            np.float32
        )
        result = {
            "predictions": self._prediction_rows(normalized, ensemble_probs, "ensemble", top_k, threshold),
            "records": [
                {"protein_id": pid, "length": len(seq), "sequence_preview": seq[:60]}
                for pid, seq in normalized
            ],
            "model": {
                "name": "ensemble",
                "branches": sorted(branch_probs),
                "weights": weights,
                "threshold": self._resolve_threshold(threshold),
                "top_k": top_k,
            },
        }
        if include_branch_predictions:
            result["branch_predictions"] = {
                name: self._prediction_rows(normalized, probs, name, top_k, threshold)
                for name, probs in branch_probs.items()
            }
        return result

    def _load_branch_states(self):
        states = {}
        ckpt_dir = self.artifact_dir / "branch_checkpoints"
        if ckpt_dir.exists():
            for path in sorted(ckpt_dir.glob("*.pt")):
                obj = torch.load(path, map_location="cpu")
                branch = obj.get("branch", path.stem) if isinstance(obj, dict) else path.stem
                states[branch] = obj.get("state_dict", obj) if isinstance(obj, dict) else obj

        for full_name in ("cafa6_high_performance_models.pt", "graph_aware_models.pt"):
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
