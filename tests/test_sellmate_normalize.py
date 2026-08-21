from misharp_hero.services.sellmate import normalize_inventory


def test_normalize_inventory_default_fields():
    raw = {
        "product_code": "P001",
        "variant_code": "V001",
        "stock_qty": "12",
        "available_qty": "10",
        "warehouse": "MAIN",
    }
    out = normalize_inventory(raw, {"P001": "123"})
    assert out["product_no"] == "123"
    assert out["stock_qty"] == 12
    assert out["inventory_key"] == "V001"
