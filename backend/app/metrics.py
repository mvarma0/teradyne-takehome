"""Quality instrumentation: one metrics row per answer, rolled up into windows with alerts.

Leading indicators of degradation (before users complain): falling confidence and retrieval
scores, more routed/insufficient answers, citation validity drops, latency spikes, rising
negative feedback / rejections / corrections. Each is compared against an absolute threshold
and against the previous window (baseline)."""

from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.db import connect, now

WINDOWS = {
    "24h": (timedelta(hours=24), "hour"),
    "7d": (timedelta(days=7), "day"),
    "30d": (timedelta(days=30), "day"),
}


def record(row: dict) -> None:
    row = {"created_at": now(), **row}
    cols = ", ".join(row)
    marks = ", ".join(f":{k}" for k in row)
    with connect() as conn:
        conn.execute(f"INSERT INTO metrics ({cols}) VALUES ({marks})", row)


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def _mean(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


def _rollup(rows: list[dict], feedback: list[dict], gaps: list[dict]) -> dict:
    n = len(rows)
    knowledge = [r for r in rows if not r["guardrail"]]
    answered = [r for r in knowledge if r["status"] == "answered"]
    rated = [f for f in feedback if f["feedback"]]
    return {
        "queries": n,
        "knowledge_queries": len(knowledge),
        "answer_rate": round(len(answered) / len(knowledge), 3) if knowledge else None,
        "routed_rate": round(sum(r["status"] == "routed" for r in knowledge) / len(knowledge), 3)
        if knowledge
        else None,
        "guardrail_blocks": sum(
            1 for r in rows if r["guardrail"] in ("prompt_injection", "off_topic")
        ),
        "guardrail_by_type": {
            g: sum(1 for r in rows if r["guardrail"] == g)
            for g in ("prompt_injection", "off_topic", "small_talk")
        },
        "mean_confidence": _mean([r["confidence"] for r in knowledge]),
        "mean_top_semantic": _mean([r["top_semantic"] for r in knowledge]),
        "mean_top_rerank": _mean([r["top_rerank"] for r in knowledge]),
        "citation_valid_ratio": _mean(
            [r["citation_valid_ratio"] for r in knowledge if r["n_citations"]]
        ),
        "uncited_dropped": sum(r["uncited_dropped"] or 0 for r in knowledge),
        "pii_redactions": sum(r["pii_redactions"] or 0 for r in rows),
        "p50_latency_ms": _pct([r["latency_ms"] for r in rows if r["latency_ms"]], 0.5),
        "p95_latency_ms": _pct([r["latency_ms"] for r in rows if r["latency_ms"]], 0.95),
        "p50_first_token_ms": _pct([r["first_token_ms"] for r in rows if r["first_token_ms"]], 0.5),
        "feedback_up": sum(f["feedback"] == "up" for f in rated),
        "feedback_down": sum(f["feedback"] == "down" for f in rated),
        "negative_feedback_rate": round(
            (
                sum(f["feedback"] == "down" for f in rated)
                + sum(g["type"] in ("rejected", "correction") for g in gaps)
            )
            / len(knowledge),
            3,
        )
        if knowledge
        else None,
        "rejections": sum(g["type"] == "rejected" for g in gaps),
        "corrections": sum(g["type"] == "correction" for g in gaps),
        "low_confidence_gaps": sum(g["type"] == "low_confidence" for g in gaps),
    }


def _load(since: str, until: str) -> tuple[list[dict], list[dict], list[dict]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM metrics WHERE created_at >= ? AND created_at < ? ORDER BY created_at",
            (since, until),
        ).fetchall()
        feedback = conn.execute(
            """SELECT feedback, created_at FROM messages WHERE role = 'assistant'
               AND created_at >= ? AND created_at < ?""",
            (since, until),
        ).fetchall()
        gaps = conn.execute(
            "SELECT type, created_at FROM gaps WHERE created_at >= ? AND created_at < ?",
            (since, until),
        ).fetchall()
    return rows, feedback, gaps


def _alerts(current: dict, baseline: dict) -> list[dict]:
    s = get_settings()
    alerts = []
    if current["knowledge_queries"] < s.alert_min_samples:
        return alerts

    def check(metric, value, threshold, message, below=True):
        # Compare the real value: a rate of 0.0 is the worst case and must alert.
        if value is None or (value >= threshold if below else value <= threshold):
            return
        alerts.append(
            {
                "metric": metric,
                "value": value,
                "threshold": threshold,
                "severity": "critical"
                if metric in ("answer_rate", "citation_valid_ratio")
                else "warning",
                "message": message,
            }
        )

    c = current
    check(
        "answer_rate",
        c["answer_rate"],
        s.alert_min_answer_rate,
        "Share of confidently answered questions is low",
    )
    check(
        "mean_confidence",
        c["mean_confidence"],
        s.alert_min_mean_confidence,
        "Mean answer confidence is low",
    )
    check(
        "citation_valid_ratio",
        c["citation_valid_ratio"],
        s.alert_min_citation_valid_ratio,
        "Answers cite excerpts that don't exist",
    )
    check(
        "negative_feedback_rate",
        c["negative_feedback_rate"],
        s.alert_max_negative_feedback_rate,
        "Users reject or correct too many answers",
        below=False,
    )
    check(
        "p95_latency_ms",
        c["p95_latency_ms"],
        s.alert_max_p95_latency_ms,
        "Slow responses (p95)",
        below=False,
    )
    if baseline["knowledge_queries"] >= s.alert_min_samples:
        for metric in ("answer_rate", "mean_confidence", "mean_top_semantic"):
            cur, base = c[metric], baseline[metric]
            if cur is not None and base and (base - cur) / base > s.alert_baseline_drop_pct:
                alerts.append(
                    {
                        "metric": metric,
                        "value": cur,
                        "threshold": round(base, 3),
                        "severity": "warning",
                        "message": f"{metric} dropped {round(100 * (base - cur) / base)}% vs "
                        "previous window (possible drift)",
                    }
                )
    return alerts


def summary(window: str = "24h") -> dict:
    span, bucket = WINDOWS.get(window, WINDOWS["24h"])
    end = datetime.now(UTC)
    start, prev_start = end - span, end - 2 * span
    iso = lambda d: d.isoformat(timespec="milliseconds")  # noqa: E731
    rows, feedback, gaps = _load(iso(start), iso(end))
    current = _rollup(rows, feedback, gaps)
    baseline = _rollup(*_load(iso(prev_start), iso(start)))

    fmt = 13 if bucket == "hour" else 10  # ISO prefix length: hour or day
    series: dict[str, list[dict]] = {}
    for r in rows:
        series.setdefault(r["created_at"][:fmt], []).append(r)
    timeseries = [
        {
            "bucket": k,
            "queries": len(v),
            "answer_rate": _rollup(v, [], [])["answer_rate"],
            "mean_confidence": _mean([x["confidence"] for x in v if not x["guardrail"]]),
            "p95_latency_ms": _pct([x["latency_ms"] for x in v if x["latency_ms"]], 0.95),
            "guardrail_blocks": sum(
                1 for x in v if x["guardrail"] in ("prompt_injection", "off_topic")
            ),
        }
        for k, v in sorted(series.items())
    ]
    return {
        "window": window,
        "from": iso(start),
        "to": iso(end),
        "current": current,
        "baseline": baseline,
        "alerts": _alerts(current, baseline),
        "timeseries": timeseries,
    }
