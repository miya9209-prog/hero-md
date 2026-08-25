from misharp_hero.services.cafe24_returns import _returned_qty_from_orders


def test_returned_qty_for_target_product():
    orders = [
        {
            "order_id": "A",
            "items": [
                {"product_no": "100", "quantity": 2, "order_status": "R40"},
                {"product_no": "200", "quantity": 1, "order_status": "R40"},
            ],
        },
        {
            "order_id": "B",
            "items": [
                {"product_no": "100", "quantity": 1, "order_status": "R40"},
            ],
        },
    ]
    order_count, qty = _returned_qty_from_orders(orders, "100")
    assert order_count == 2
    assert qty == 3
