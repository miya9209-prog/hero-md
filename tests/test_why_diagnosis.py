import pandas as pd

from misharp_hero.hero_score import diagnose_with_why


def test_why_contains_metrics_and_action():
    history = pd.DataFrame(
        {
            "views": [100, 200, 300, 400, 500],
            "cvr": [0.01, 0.015, 0.02, 0.025, 0.03],
            "rpv": [200, 400, 600, 800, 1000],
            "qty": [1, 2, 3, 4, 5],
            "revenue": [10000, 20000, 30000, 40000, 50000],
        }
    )
    out = diagnose_with_why(
        {
            "views": 250,
            "cvr": 0.04,
            "rpv": 1200,
            "qty": 5,
            "revenue": 80000,
            "hero_score": 78,
            "cart_rate": 0.07,
        },
        history,
    )
    assert out["diagnosis"] in {"숨은 HERO", "HERO 유력"}
    assert "구매전환율(CVR)" in out["why"]
    assert "조회당 매출(RPV)" in out["why"]
    assert out["recommended_action"]


def test_return_warning_does_not_change_score_but_changes_action():
    out = diagnose_with_why(
        {
            "views": 2000,
            "cvr": 0.05,
            "rpv": 2500,
            "qty": 30,
            "revenue": 1000000,
            "hero_score": 90,
            "return_rate": 0.12,
        },
        None,
    )
    assert out["diagnosis"] == "HERO"
    assert "반품률" in out["why"]
    assert "반품사유" in out["recommended_action"]
