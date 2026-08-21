from misharp_hero.hero_score import postlaunch_score, hero_grade, diagnose


def test_high_signal_score():
    row = {
        "views": 2500,
        "cvr": 0.05,
        "rpv": 2600,
        "cart_rate": 0.09,
        "qty": 70,
        "revenue": 3_000_000,
        "sera_click_value": 80,
    }
    score = postlaunch_score(row)
    assert score >= 70
    assert hero_grade(score) in {"🔥 HERO", "💎 HERO 유력"}


def test_hidden_hero():
    assert "숨은 HERO" in diagnose(300, 0.04)
