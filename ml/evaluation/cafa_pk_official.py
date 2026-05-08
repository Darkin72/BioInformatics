"""Wrapper utilities for the official CAFA-evaluator-PK package.

This module does not reimplement the CAFA metric. It prepares local files in the
format expected by https://github.com/claradepaolis/CAFA-evaluator-PK and then
invokes that evaluator either as an installed Python package or from a cloned
source tree.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def write_ground_truth(
    train_terms_path: Path,
    protein_ids_path: Path,
    output_path: Path,
    terms_of_interest_path: Path | None = None,
) -> int:
    import pandas as pd

    protein_ids = read_id_list(protein_ids_path)
    terms = pd.read_csv(
        train_terms_path,
        sep="\t",
        header=None,
        names=["protein_id", "go_term", "aspect"],
        usecols=[0, 1, 2],
    )
    terms = terms[terms["protein_id"].isin(protein_ids)]
    if terms_of_interest_path is not None:
        toi = set(read_id_list(terms_of_interest_path))
        terms = terms[terms["go_term"].isin(toi)]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    terms[["protein_id", "go_term"]].drop_duplicates().to_csv(
        output_path,
        sep="\t",
        header=False,
        index=False,
    )
    return len(terms)


def write_terms_of_interest(go_terms_path: Path, output_path: Path) -> int:
    terms = json.loads(go_terms_path.read_text())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(terms) + "\n")
    return len(terms)


def normalize_prediction_file(input_path: Path, output_dir: Path, method_name: str) -> Path:
    import pandas as pd

    preds = pd.read_csv(
        input_path,
        sep="\t",
        header=None,
        names=["protein_id", "go_term", "score"],
        usecols=[0, 1, 2],
    )
    preds = preds.dropna()
    preds["score"] = preds["score"].astype(float).clip(lower=0.0, upper=1.0)
    preds = preds[preds["score"] > 0.0]
    preds = preds.sort_values(["protein_id", "score"], ascending=[True, False])

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{method_name}.tsv"
    preds.to_csv(out_path, sep="\t", header=False, index=False)
    return out_path


def run_cafa_evaluator(
    obo_file: Path,
    prediction_dir: Path,
    ground_truth_file: Path,
    output_dir: Path,
    evaluator_src: Path | None = None,
    ia_file: Path | None = None,
    terms_of_interest_file: Path | None = None,
    known_annotations_file: Path | None = None,
    threshold_step: float = 0.01,
    max_terms: int | None = None,
    threads: int = 4,
    no_orphans: bool = False,
    norm: str = "cafa",
    prop: str = "max",
    log_level: str = "info",
) -> subprocess.CompletedProcess[str]:
    if evaluator_src is None:
        module_or_script = ["-m", "cafaeval"]
    else:
        module_or_script = [str(evaluator_src / "src" / "cafaeval" / "__main__.py")]

    cmd = [
        sys.executable,
        *module_or_script,
        str(obo_file),
        str(prediction_dir),
        str(ground_truth_file),
        "-out_dir",
        str(output_dir),
        "-th_step",
        str(threshold_step),
        "-threads",
        str(threads),
        "-norm",
        norm,
        "-prop",
        prop,
        "-log_level",
        log_level,
    ]
    if ia_file is not None:
        cmd.extend(["-ia", str(ia_file)])
    if terms_of_interest_file is not None:
        cmd.extend(["-toi", str(terms_of_interest_file)])
    if known_annotations_file is not None:
        cmd.extend(["-known", str(known_annotations_file)])
    if max_terms is not None:
        cmd.extend(["-max_terms", str(max_terms)])
    if no_orphans:
        cmd.append("-no_orphans")

    output_dir.mkdir(parents=True, exist_ok=True)
    print("[CAFA-EVAL] Running:")
    print(" ".join(cmd))
    return subprocess.run(cmd, check=True, text=True, capture_output=False)


def read_id_list(path: Path) -> list[str]:
    ids: list[str] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        ids.append(line.split()[0])
    return ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and run CAFA-evaluator-PK for offline CAFA benchmarks."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prep = subparsers.add_parser("prepare", help="Prepare evaluator input files.")
    prep.add_argument("--train-terms", required=True, type=Path)
    prep.add_argument("--test-ids", required=True, type=Path)
    prep.add_argument("--go-terms-json", required=True, type=Path)
    prep.add_argument("--prediction-tsv", required=True, type=Path)
    prep.add_argument("--work-dir", required=True, type=Path)
    prep.add_argument("--method-name", default="baseline")

    run = subparsers.add_parser("run", help="Run official CAFA-evaluator-PK.")
    run.add_argument("--obo-file", required=True, type=Path)
    run.add_argument("--prediction-dir", required=True, type=Path)
    run.add_argument("--ground-truth", required=True, type=Path)
    run.add_argument("--out-dir", required=True, type=Path)
    run.add_argument("--evaluator-src", type=Path)
    run.add_argument("--ia-file", type=Path)
    run.add_argument("--terms-of-interest", type=Path)
    run.add_argument("--known-annotations", type=Path)
    run.add_argument("--threshold-step", default=0.01, type=float)
    run.add_argument("--max-terms", type=int)
    run.add_argument("--threads", default=4, type=int)
    run.add_argument("--no-orphans", action="store_true")
    run.add_argument("--norm", default="cafa", choices=["cafa", "pred", "gt"])
    run.add_argument("--prop", default="max", choices=["max", "fill"])
    run.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error", "critical"],
    )

    all_cmd = subparsers.add_parser("prepare-and-run", help="Prepare files and run evaluator.")
    all_cmd.add_argument("--train-terms", required=True, type=Path)
    all_cmd.add_argument("--test-ids", required=True, type=Path)
    all_cmd.add_argument("--go-terms-json", required=True, type=Path)
    all_cmd.add_argument("--prediction-tsv", required=True, type=Path)
    all_cmd.add_argument("--work-dir", required=True, type=Path)
    all_cmd.add_argument("--method-name", default="baseline")
    all_cmd.add_argument("--obo-file", required=True, type=Path)
    all_cmd.add_argument("--evaluator-src", type=Path)
    all_cmd.add_argument("--ia-file", type=Path)
    all_cmd.add_argument("--threshold-step", default=0.01, type=float)
    all_cmd.add_argument("--max-terms", type=int)
    all_cmd.add_argument("--threads", default=4, type=int)
    all_cmd.add_argument("--no-orphans", action="store_true")
    all_cmd.add_argument("--log-level", default="info")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.command in {"prepare", "prepare-and-run"}:
        work_dir = args.work_dir
        gt_path = work_dir / "ground_truth.tsv"
        toi_path = work_dir / "terms_of_interest.tsv"
        pred_dir = work_dir / "predictions"

        n_toi = write_terms_of_interest(args.go_terms_json, toi_path)
        n_gt = write_ground_truth(args.train_terms, args.test_ids, gt_path, toi_path)
        pred_path = normalize_prediction_file(args.prediction_tsv, pred_dir, args.method_name)
        print(f"[CAFA-EVAL] Wrote {n_toi:,} terms of interest: {toi_path}")
        print(f"[CAFA-EVAL] Wrote {n_gt:,} ground-truth rows: {gt_path}")
        print(f"[CAFA-EVAL] Wrote prediction file: {pred_path}")

        if args.command == "prepare":
            return

        run_cafa_evaluator(
            obo_file=args.obo_file,
            prediction_dir=pred_dir,
            ground_truth_file=gt_path,
            output_dir=work_dir / "results",
            evaluator_src=args.evaluator_src,
            ia_file=args.ia_file,
            terms_of_interest_file=toi_path,
            threshold_step=args.threshold_step,
            max_terms=args.max_terms,
            threads=args.threads,
            no_orphans=args.no_orphans,
            log_level=args.log_level,
        )
        return

    run_cafa_evaluator(
        obo_file=args.obo_file,
        prediction_dir=args.prediction_dir,
        ground_truth_file=args.ground_truth,
        output_dir=args.out_dir,
        evaluator_src=args.evaluator_src,
        ia_file=args.ia_file,
        terms_of_interest_file=args.terms_of_interest,
        known_annotations_file=args.known_annotations,
        threshold_step=args.threshold_step,
        max_terms=args.max_terms,
        threads=args.threads,
        no_orphans=args.no_orphans,
        norm=args.norm,
        prop=args.prop,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
