from app.evals import calibrate


def _case(confidence: float, answerable: bool = True, faithfulness: float | None = 1.0) -> dict:
    return {
        "confidence": confidence,
        "answerable": answerable,
        "cited_expected": answerable,
        "faithfulness": faithfulness if answerable else None,
    }


def test_threshold_separates_good_answers_from_unanswerable_ones():
    results = [_case(0.8), _case(0.7), _case(0.62), _case(0.5, answerable=False), _case(0.3, False)]
    cal = calibrate(results)
    assert cal["deserve_answer"] == 3
    # 0.55 and 0.60 both separate perfectly; the middle of the tie rounds up (toward routing).
    assert cal["optimal_range"] == [0.55, 0.6]
    assert cal["suggested_threshold"] == 0.6
    row = next(r for r in cal["sweep"] if r["threshold"] == 0.6)
    assert row["false_confident"] == 0 and row["needless_route"] == 0 and row["accuracy"] == 1.0


def test_blocked_cases_without_confidence_are_skipped():
    blocked = {"confidence": None, "answerable": False, "cited_expected": None}
    assert calibrate([_case(0.9), _case(0.2, answerable=False), blocked])["cases"] == 2


def test_false_confidence_costs_more_than_a_needless_route():
    # One unfaithful answer at 0.6 and one good answer at 0.45: lowering the threshold to 0.45
    # would show the bad answer as confident, so the sweep keeps it above 0.6.
    results = [_case(0.9), _case(0.6, faithfulness=0.2), _case(0.45)]
    cal = calibrate(results)
    assert cal["suggested_threshold"] > 0.6
    by_t = {r["threshold"]: r for r in cal["sweep"]}
    assert by_t[0.45]["cost"] == 2 and by_t[0.65]["cost"] == 1
