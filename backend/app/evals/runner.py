"""Offline evaluation over golden / synthetic question sets.

Per case: retrieval hit@k and MRR against expected source files, whether an expected source
was actually cited, citation validity, answerability (confident vs. expected), keyword recall,
and an LLM judge for faithfulness (answer supported by cited excerpts) and relevance.
"""

import json
import logging
import threading
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.answer.chat import ChatRequest, answer
from app.config import BACKEND_DIR, get_settings
from app.db.chat_repo import new_id, now
from app.db.sqlite import connect
from app.llm.factory import llm_identity, structured_llm

log = logging.getLogger(__name__)
EVAL_DIR = BACKEND_DIR / "eval"
DATASETS = {"golden": EVAL_DIR / "golden.jsonl", "synthetic": EVAL_DIR / "synthetic.jsonl"}
_running = threading.Lock()


class Judgement(BaseModel):
    reason: str = Field(description="One sentence justification")
    faithfulness: int = Field(description="0-10: every statement is supported by the excerpts")
    relevance: int = Field(description="0-10: the answer addresses the question")


_JUDGE = ChatPromptTemplate.from_messages(
    [
        ("system", "You grade answers from a retrieval-augmented assistant. Be strict."),
        (
            "human",
            "Question: {question}\n\nExcerpts the answer cited:\n{excerpts}\n\nAnswer:\n{answer}",
        ),
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
    cited = [c for c in payload["citations"] if c["n"] in payload.get("cited", [])]
    if not cited:
        return {"faithfulness": None, "relevance": None, "judge_reason": "no citations"}
    excerpts = "\n\n".join(f"[{c['n']}] {c['snippet']}" for c in cited)
    try:
        j: Judgement = (_JUDGE | structured_llm(Judgement)).invoke(
            {"question": question, "excerpts": excerpts, "answer": payload["answer"]}
        )
        return {
            "faithfulness": _unit(j.faithfulness),
            "relevance": _unit(j.relevance),
            "judge_reason": j.reason,
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
