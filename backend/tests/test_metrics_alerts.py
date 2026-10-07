from app.metrics import _alerts

HEALTHY = {
    "knowledge_queries": 10,
    "answer_rate": 0.9,
    "mean_confidence": 0.8,
    "citation_valid_ratio": 1.0,
    "negative_feedback_rate": 0.0,
    "p95_latency_ms": 1000,
    "mean_top_semantic": 0.6,
}
NO_BASELINE = {"knowledge_queries": 0}


def _metrics(current: dict, baseline: dict = NO_BASELINE) -> set[str]:
    return {a["metric"] for a in _alerts(current, baseline)}


def test_healthy_window_raises_no_alerts():
    assert _metrics(HEALTHY) == set()


def test_zero_rates_alert_like_any_other_low_value():
    # A total outage (nothing answered, zero confidence, no valid citations) is the worst
    # case and must alert even without a baseline window to compare against.
    outage = {**HEALTHY, "answer_rate": 0.0, "mean_confidence": 0.0, "citation_valid_ratio": 0.0}
    assert _metrics(outage) == {"answer_rate", "mean_confidence", "citation_valid_ratio"}
    low = {**HEALTHY, "answer_rate": 0.3, "mean_confidence": 0.3, "citation_valid_ratio": 0.5}
    assert _metrics(low) == {"answer_rate", "mean_confidence", "citation_valid_ratio"}


def test_upper_bound_metrics_alert_above_threshold_only():
    assert _metrics({**HEALTHY, "negative_feedback_rate": 0.5, "p95_latency_ms": 60000}) == {
        "negative_feedback_rate",
        "p95_latency_ms",
    }


def test_missing_values_and_small_samples_stay_quiet():
    empty = {**HEALTHY, "answer_rate": None, "mean_confidence": None, "p95_latency_ms": None}
    assert _metrics(empty) == set()
    assert _metrics({**HEALTHY, "knowledge_queries": 2, "answer_rate": 0.0}) == set()
