from misharp_hero.services.cafe24_analytics import merge_metric_rows


def test_merge_metrics():
    rows = merge_metric_rows(
        [{"product_no": 1, "product_name": "A", "count": 100}],
        [{"product_no": 1, "order_count": 3, "order_product_count": 4, "order_amount": 120000}],
        [{"product_no": 1, "add_cart_count": 10, "add_cart_rate": 10}],
    )
    assert rows[0]["views"] == 100
    assert rows[0]["cart_count"] == 10
    assert rows[0]["cart_rate"] == 0.10
    assert rows[0]["order_count"] == 3
    assert rows[0]["qty"] == 4
