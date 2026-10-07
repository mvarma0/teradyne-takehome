"""Offline evals over golden + synthetic question sets, with an LLM judge.

CLI: uv run python -m app.evals [--dataset golden|synthetic|all] [--synthesize N] [--calibrate]"""

import argparse
import json
import logging
import random
import sys
import threading
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.answer import ChatRequest, answer
from app.config import BACKEND_DIR, get_settings
from app.db import connect, init_db, new_id, now
from app.llm import llm_identity, structured_llm
from app.search import all_chunks, chunk_texts

# ---- runner -------------------------------------------------------------------------------
# Offline evaluation over golden / synthetic question sets.
#
# Per case: retrieval hit@k and MRR against expected source files, whether an expected source
# was actually cited, citation validity, answerability (confident vs. expected), keyword recall,
# and an LLM judge for faithfulness (answer supported by cited excerpts) and relevance.

log = logging.getLogger(__name__)
EVAL_DIR = BACKEND_DIR / "eval"
DATASETS = {"golden": EVAL_DIR / "golden.jsonl", "synthetic": EVAL_DIR / "synthetic.jsonl"}
_running = threading.Lock()


class ClaimVerdict(BaseModel):
    claim: int = Field(description="Claim number as listed")
    supported: bool = Field(description="True if the cited excerpts state this claim")


class Judgement(BaseModel):
    reason: str = Field(description="One sentence justification")
    verdicts: list[ClaimVerdict] = Field(description="One verdict per numbered claim")
    relevance: int = Field(description="0-10: how well the answer addresses the question")


# Faithfulness is judged per claim against the full text of the excerpts that claim cites,
# and only asks "is it stated there?". Completeness belongs to relevance, not faithfulness.
_JUDGE = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You check answers from a retrieval-augmented assistant.\n"
            "For each numbered claim, decide if the excerpts it cites state it. A claim is "
            "supported when the excerpts state it directly or it is a faithful paraphrase or "
            "summary of them (same facts, numbers, names and dates). It is unsupported if it "
            "adds facts, numbers, names or conclusions the excerpts don't contain. Do not "
            "penalize a claim for being brief or for leaving out details.\n"
            "Separately, rate relevance 0-10: does the answer address what was asked?",
        ),
        ("human", "Question: {question}\n\nExcerpts:\n{excerpts}\n\nClaims:\n{claims}"),
    ]
)


def load_cases(dataset: str) -> list[dict]:
    paths = list(DATASETS.values()) if dataset == "all" else [DATASETS[dataset]]
    cases = []
    for path in paths:
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    case = json.loads(line)
                    case.setdefault("dataset", path.stem)
                    cases.append(case)
    return cases


def _unit(score: float) -> float:
    """Judge scores are requested on 0-10; small models sometimes answer on 0-100."""
    scale = 100 if score > 10 else 10
    return round(max(0.0, min(1.0, score / scale)), 3)


def _judge(question: str, payload: dict) -> dict:
    claims = [c for c in payload.get("claims", []) if c["kind"] == "fact" and c["citations"]]
    if not claims:
        return {"faithfulness": None, "relevance": None, "judge_reason": "no cited claims"}
    by_n = {c["n"]: c for c in payload["citations"]}
    used = sorted({n for c in claims for n in c["citations"] if n in by_n})
    full = chunk_texts([by_n[n]["chunk_id"] for n in used])
    excerpts = "\n\n".join(
        f"[{n}] {full.get(by_n[n]['chunk_id'], by_n[n]['snippet'])}" for n in used
    )
    listed = "\n".join(
        f"{i}. {c['text']} (cites {', '.join(f'[{n}]' for n in c['citations'])})"
        for i, c in enumerate(claims, start=1)
    )
    try:
        j: Judgement = (_JUDGE | structured_llm(Judgement)).invoke(
            {"question": question, "excerpts": excerpts, "claims": listed}
        )
        verdicts = {v.claim: v.supported for v in j.verdicts if 1 <= v.claim <= len(claims)}
        supported = sum(verdicts.get(i, False) for i in range(1, len(claims) + 1))
        return {
            "faithfulness": round(supported / len(claims), 3),
            "relevance": _unit(j.relevance),
            "judge_reason": j.reason,
            "claims_judged": len(claims),
            "claims_supported": supported,
        }
    except Exception as exc:
        return {"faithfulness": None, "relevance": None, "judge_reason": f"judge failed: {exc}"}


def evaluate_case(case: dict) -> tuple[dict, dict]:
    payload = answer(ChatRequest(message=case["question"], chat=False, persist=False, route=False))
    expected = set(case.get("expected_sources", []))
    retrieved = [c["source_file"] for c in payload["citations"]]
    cited_files = {
        c["source_file"] for c in payload["citations"] if c["n"] in payload.get("cited", [])
    }
    rank = next((i for i, f in enumerate(retrieved, start=1) if f in expected), None)
    answerable = case.get("answerable", True)
    keywords = case.get("expected_keywords", [])
    text = (payload["answer"] or "").lower()
    stats = payload.get("citation_stats") or {}
    result = {
        "answerable": answerable,
        "confident": payload["confident"],
        "confidence": payload["confidence"],
        "status": payload["status"],
        "hit": bool(rank) if expected else None,
        "reciprocal_rank": (1 / rank if rank else 0.0) if expected else None,
        "cited_expected": bool(cited_files & expected) if expected else None,
        "answerability_correct": bool(payload["confident"]) == answerable,
        "keyword_recall": (sum(k.lower() in text for k in keywords) / len(keywords))
        if keywords
        else None,
        "citation_valid_ratio": (stats["valid"] / stats["total"]) if stats.get("total") else None,
        "latency_ms": payload["latency_ms"],
        "retrieved": retrieved,
        **(_judge(case["question"], payload) if answerable else {}),
    }
    return result, payload


def _mean(values: list) -> float | None:
    values = [float(v) for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


def summarize(results: list[dict]) -> dict:
    answerable = [r for r in results if r["answerable"]]
    return {
        "cases": len(results),
        "hit_rate": _mean([r["hit"] for r in answerable]),
        "mrr": _mean([r["reciprocal_rank"] for r in answerable]),
        "cited_expected_rate": _mean([r["cited_expected"] for r in answerable]),
        "answerability_accuracy": _mean([r["answerability_correct"] for r in results]),
        "unanswerable_refusal_rate": _mean(
            [not r["confident"] for r in results if not r["answerable"]]
        ),
        "keyword_recall": _mean([r["keyword_recall"] for r in answerable]),
        "faithfulness": _mean([r.get("faithfulness") for r in answerable]),
        "relevance": _mean([r.get("relevance") for r in answerable]),
        "citation_valid_ratio": _mean([r["citation_valid_ratio"] for r in results]),
        "mean_confidence": _mean([r["confidence"] for r in results]),
        "p50_latency_ms": sorted(r["latency_ms"] for r in results)[len(results) // 2]
        if results
        else None,
    }


def run(dataset: str = "golden", run_id: str | None = None) -> dict:
    cases = load_cases(dataset)
    if not cases:
        raise ValueError(f"No eval cases found for dataset '{dataset}' in {EVAL_DIR}")
    s = get_settings()
    run_id = run_id or new_id()
    config = {
        "llm": llm_identity(),
        "embeddings": f"{s.embedding_provider}:{s.embedding_model}",
        "reranker": s.reranker,
        "top_k": s.top_k,
        "threshold": s.confidence_threshold,
    }
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO eval_runs (id, dataset, status, started_at, config_json) "
            "VALUES (?, ?, 'running', ?, ?)",
            (run_id, dataset, now(), json.dumps(config)),
        )
        conn.execute(
            "UPDATE eval_runs SET config_json = ? WHERE id = ?", (json.dumps(config), run_id)
        )
    results = []
    try:
        for case in cases:
            result, payload = evaluate_case(case)
            results.append(result)
            with connect() as conn:
                conn.execute(
                    "INSERT INTO eval_results (run_id, case_id, question, expected_json, answer,"
                    " result_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        case.get("id", ""),
                        case["question"],
                        json.dumps(case),
                        payload["answer"],
                        json.dumps(result),
                    ),
                )
        summary = summarize(results)
        with connect() as conn:
            conn.execute(
                "UPDATE eval_runs SET status='completed', finished_at=?, summary_json=? WHERE id=?",
                (now(), json.dumps(summary), run_id),
            )
        return {"run_id": run_id, "summary": summary}
    except Exception as exc:
        log.exception("eval run failed")
        with connect() as conn:
            conn.execute(
                "UPDATE eval_runs SET status='failed', finished_at=?, error=? WHERE id=?",
                (now(), str(exc), run_id),
            )
        raise


def start_background(dataset: str) -> str:
    if not load_cases(dataset):
        raise ValueError(f"No eval cases found for dataset '{dataset}'")
    if not _running.acquire(blocking=False):
        raise RuntimeError("An eval run is already in progress")
    run_id = new_id()

    def _target():
        try:
            run(dataset, run_id)
        except Exception:
            pass  # recorded on the run row
        finally:
            _running.release()

    with connect() as conn:
        conn.execute(
            "INSERT INTO eval_runs (id, dataset, status, started_at) VALUES (?, ?, 'running', ?)",
            (run_id, dataset, now()),
        )
    threading.Thread(target=_target, daemon=True).start()
    return run_id


def list_runs(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT r.*, (SELECT COUNT(*) FROM eval_results e WHERE e.run_id = r.id) AS done "
            "FROM eval_runs r ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_decode_run(r) for r in rows]


def _decode_run(row: dict) -> dict:
    out = dict(row)
    out["config"] = json.loads(out.pop("config_json") or "null")
    out["summary"] = json.loads(out.pop("summary_json") or "null")
    return out


def get_run(run_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM eval_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        results = conn.execute(
            "SELECT case_id, question, expected_json, answer, result_json FROM eval_results "
            "WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
    out = _decode_run(row)
    out["total"] = len(load_cases(out["dataset"]))
    out["results"] = [
        {
            "case_id": r["case_id"],
            "question": r["question"],
            "answer": r["answer"],
            "expected": json.loads(r["expected_json"]),
            **json.loads(r["result_json"]),
        }
        for r in results
    ]
    return out


def dataset_info() -> dict:
    return {name: len(load_cases(name)) for name in DATASETS} | {
        "path": str(Path(EVAL_DIR).relative_to(BACKEND_DIR))
    }


# ---- synthesize ---------------------------------------------------------------------------
# Generate a synthetic eval set from ingested chunks: the LLM writes one question per
# sampled chunk that the chunk answers; the chunk's file becomes the expected source.


class SyntheticCase(BaseModel):
    question: str = Field(description="A specific question an employee might ask")
    expected_keywords: list[str] = Field(description="2-4 short facts the answer must contain")


_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Write one realistic, specific question that the excerpt below fully "
            "answers, as an engineer at the company would ask it. Do not mention "
            "'the excerpt' or 'the document'. Also list 2-4 short key facts "
            "(names, numbers, dates) the correct answer must contain.",
        ),
        ("human", "{excerpt}"),
    ]
)


# ---- threshold calibration ----------------------------------------------------------------
# Sweep CONFIDENCE_THRESHOLD over a finished run. A case "deserves" a confident answer when it
# is answerable, cites an expected source and the judge finds its claims supported. Showing a
# wrong answer as confident costs more than routing a good one, so false confidence weighs 2x.
# Guardrail-blocked cases have no confidence and are left out.

FALSE_CONFIDENT_COST = 2.0


def _deserves_answer(r: dict) -> bool:
    if not r["answerable"] or r.get("cited_expected") is False:
        return False
    if r.get("faithfulness") is None:  # refused, or the judge failed: trust the citation only
        return bool(r.get("cited_expected")) and "judge failed" in r.get("judge_reason", "")
    return r["faithfulness"] >= 0.7


def calibrate(results: list[dict], thresholds: list[float] | None = None) -> dict:
    thresholds = thresholds or [round(0.30 + 0.05 * i, 2) for i in range(11)]  # 0.30..0.80
    # Guardrail-blocked cases never get a confidence score, so the threshold doesn't apply.
    labelled = [
        (r["confidence"], _deserves_answer(r)) for r in results if r["confidence"] is not None
    ]
    sweep = []
    for t in thresholds:
        false_confident = sum(c >= t and not good for c, good in labelled)
        needless_route = sum(c < t and good for c, good in labelled)
        sweep.append(
            {
                "threshold": t,
                "false_confident": false_confident,
                "needless_route": needless_route,
                "accuracy": round(1 - (false_confident + needless_route) / len(labelled), 3),
                "cost": FALSE_CONFIDENT_COST * false_confident + needless_route,
            }
        )
    # Lowest cost wins; among tied thresholds take the middle one, the cut with the widest
    # margin on both sides (rounding up, toward routing).
    lowest = min(row["cost"] for row in sweep)
    tied = [row for row in sweep if row["cost"] == lowest]
    best = tied[len(tied) // 2]
    return {
        "cases": len(labelled),
        "deserve_answer": sum(good for _, good in labelled),
        "suggested_threshold": best["threshold"],
        "optimal_range": [tied[0]["threshold"], tied[-1]["threshold"]],
        "sweep": sweep,
    }


def latest_results(dataset: str | None = None) -> tuple[str, list[dict]]:
    """Results of the newest completed run (optionally for one dataset)."""
    query = "SELECT id FROM eval_runs WHERE status = 'completed'"
    params: tuple = ()
    if dataset:
        query, params = query + " AND dataset = ?", (dataset,)
    with connect() as conn:
        row = conn.execute(query + " ORDER BY started_at DESC LIMIT 1", params).fetchone()
        if not row:
            raise ValueError("No completed eval run to calibrate from")
        rows = conn.execute(
            "SELECT result_json FROM eval_results WHERE run_id = ?", (row["id"],)
        ).fetchall()
    return row["id"], [json.loads(r["result_json"]) for r in rows]


def synthesize(n: int = 20, seed: int = 7) -> int:
    chunks = [c for c in all_chunks() if len(c.page_content) > 300]
    by_doc: dict[str, list] = {}
    for c in chunks:
        by_doc.setdefault(c.metadata["doc_id"], []).append(c)
    rng = random.Random(seed)
    pools = [rng.sample(v, len(v)) for v in by_doc.values()]
    rng.shuffle(pools)
    picked = []  # round-robin across documents for coverage
    while len(picked) < n and any(pools):
        for pool in pools:
            if pool and len(picked) < n:
                picked.append(pool.pop())
    results = (_PROMPT | structured_llm(SyntheticCase)).batch(
        [{"excerpt": c.page_content[:2000]} for c in picked],
        config={"max_concurrency": 4},
        return_exceptions=True,
    )
    lines = []
    for i, (chunk, res) in enumerate(zip(picked, results, strict=True), start=1):
        if isinstance(res, Exception):
            log.warning("synthesis failed for %s: %s", chunk.metadata["chunk_id"], res)
            continue
        lines.append(
            json.dumps(
                {
                    "id": f"syn-{i:02d}",
                    "question": res.question,
                    "answerable": True,
                    "expected_sources": [chunk.metadata["source_file"]],
                    "expected_keywords": res.expected_keywords,
                }
            )
        )
    DATASETS["synthetic"].parent.mkdir(parents=True, exist_ok=True)
    DATASETS["synthetic"].write_text("\n".join(lines) + "\n")
    return len(lines)


# ---- main ---------------------------------------------------------------------------------
# CLI: uv run python -m app.evals [--dataset golden|synthetic|all] [--synthesize N] [--calibrate]

TARGETS = {"hit_rate": 0.8, "faithfulness": 0.7, "answerability_accuracy": 0.7}


def main() -> None:
    ap = argparse.ArgumentParser(description="Run offline RAG evals")
    ap.add_argument("--dataset", default="golden", choices=["golden", "synthetic", "all"])
    ap.add_argument("--synthesize", type=int, metavar="N", help="generate N synthetic cases first")
    ap.add_argument(
        "--calibrate",
        action="store_true",
        help="sweep CONFIDENCE_THRESHOLD over the latest completed run instead of running one",
    )
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    init_db()
    if args.calibrate:
        run_id, results = latest_results()
        print(json.dumps({"run_id": run_id, **calibrate(results)}, indent=2))
        return
    if args.synthesize:
        print(f"generated {synthesize(args.synthesize)} synthetic cases")
    result = run(args.dataset)
    summary = result["summary"]
    print(json.dumps(summary, indent=2))
    _, results = latest_results()
    cal = calibrate(results)
    print(
        f"threshold: current {get_settings().confidence_threshold}, "
        f"suggested {cal['suggested_threshold']} ({cal['deserve_answer']}/{cal['cases']} cases "
        "deserve a confident answer; see --calibrate for the sweep)"
    )
    failed = [k for k, t in TARGETS.items() if summary.get(k) is not None and summary[k] < t]
    if failed:
        print(f"BELOW TARGET: {failed} (targets {TARGETS})")
        sys.exit(1)


if __name__ == "__main__":
    main()
