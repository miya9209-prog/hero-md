from misharp_hero.services.new_product_discovery import extract_product_nos


def test_extract_product_nos_from_cafe24_links():
    html = """
    <a href="/product/detail.html?product_no=29059&cate_no=1">A</a>
    <a href="/product/sample-name/29060/category/12/display/1/">B</a>
    """
    assert extract_product_nos(html) == {"29059", "29060"}
