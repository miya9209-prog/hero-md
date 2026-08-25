from misharp_hero.hero_score import fallback_postlaunch_score
from misharp_hero.services.cafe24_admin import normalize_product


def test_fixed_hero_score_weights():
    # CVR만 100점이면 전체 HERO Score는 확정 가중치 30점이어야 한다.
    score = fallback_postlaunch_score(views=0, cvr=0.04, rpv=0, qty=0, revenue=0)
    assert score == 30.0


def test_cafe24_product_operational_fields():
    row = normalize_product({
        "product_no": 123,
        "product_name": "테스트",
        "price": "39,000",
        "retail_price": "49,000",
        "display": True,
        "selling": False,
        "created_date": "2026-08-20T10:00:00+09:00",
        "updated_date": "2026-08-21T11:00:00+09:00",
    })
    assert row["product_no"] == "123"
    assert row["selling_price"] == 39000
    assert row["retail_price"] == 49000
    assert row["display"] == "T"
    assert row["selling"] == "F"
    assert row["cafe24_created_at"] is not None
    assert row["cafe24_updated_at"] is not None
