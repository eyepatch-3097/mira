from urllib.parse import urlparse

def categorize_url(url: str) -> str:
    path = (urlparse(url).path or "").lower()

    blog_markers = ["/blog", "/blogs", "/article", "/articles", "/news", "/post"]
    product_markers = ["/product", "/products", "/p/", "/sku", "/item", "/collections"]

    if any(m in path for m in blog_markers):
        return "blog"
    if any(m in path for m in product_markers):
        return "product"
    return "info"
