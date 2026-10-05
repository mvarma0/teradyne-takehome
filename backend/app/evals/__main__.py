"""CLI: uv run python -m app.evals [--dataset golden|synthetic|all] [--synthesize N]"""

import argparse
import json
import logging
import sys

from app.db.sqlite import init_db
from app.evals.runner import run
from app.evals.synthesize import synthesize

TARGETS = {"hit_rate": 0.8, "faithfulness": 0.7, "answerability_accuracy": 0.7}


def main() -> None:
    ap = argparse.ArgumentParser(description="Run offline RAG evals")
    ap.add_argument("--dataset", default="golden", choices=["golden", "synthetic", "all"])
    ap.add_argument("--synthesize", type=int, metavar="N", help="generate N synthetic cases first")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    init_db()
    if args.synthesize:
        print(f"generated {synthesize(args.synthesize)} synthetic cases")
    summary = run(args.dataset)["summary"]
    print(json.dumps(summary, indent=2))
    failed = [k for k, t in TARGETS.items() if summary.get(k) is not None and summary[k] < t]
    if failed:
        print(f"BELOW TARGET: {failed} (targets {TARGETS})")
        sys.exit(1)


if __name__ == "__main__":
    main()
