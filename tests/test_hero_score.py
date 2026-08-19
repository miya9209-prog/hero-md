from misharp_hero.hero_score import prelaunch_score, hero_grade, diagnose

def test_prelaunch_score_range():
    s = prelaunch_score(
        focus=True, dna_score=90, margin_rate=40,
        season_score=90, reorder_score=80, content_score=85, md_score=90
    )
    assert 0 <= s <= 100
    assert s > 70

def test_grade():
    assert "HERO" in hero_grade(90)
    assert hero_grade(50) == "재검토"

def test_diagnose_fallback():
    assert diagnose(2000, 0.04) == "HERO"
    assert "숨은" in diagnose(200, 0.04)
