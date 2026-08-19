from misharp_hero.services.sera_import import extract_product_no

def test_extract_query():
    assert extract_product_no("https://misharp.co.kr/product/detail.html?product_no=29019") == "29019"

def test_extract_path():
    assert extract_product_no("https://misharp.co.kr/product/abc/29019/") == "29019"
