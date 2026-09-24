import json
from bs4 import BeautifulSoup
from scanner.fetch_sites import extract_pricing, strip_html


def test_extract_pricing_public_tiers():
    html_text = """
    Our Plans:
    Starter Plan - $49/mo
    Pro Plan - $199/mo
    Enterprise - Custom pricing
    """
    soup = BeautifulSoup(html_text, "lxml")
    p = extract_pricing(soup, html_text)
    assert p["has_public_pricing"] is True
    assert any("$49" in price for price in p["price_points"])
    assert "Starter" in p["plans"]
    assert "Pro" in p["plans"]


def test_extract_pricing_sales_led():
    html_text = """
    Enterprise AI Platform.
    Empowering Fortune 500 teams to scale intelligence.
    Book a demo today or contact sales for custom deployment.
    """
    soup = BeautifulSoup(html_text, "lxml")
    p = extract_pricing(soup, html_text)
    assert p["has_public_pricing"] is False
    assert p["is_sales_led"] is True
    assert "Sales-Led" in p["summary"]


def test_strip_html_next_data_recovery():
    next_json = json.dumps({
        "props": {
            "pageProps": {
                "headline": "Autonomous AI Agent Orchestration for FinTech",
                "features": ["Automated compliance checks", "Real-time transaction scoring"],
            }
        }
    })
    html = f"""
    <html>
      <head><title>NextGen AI</title></head>
      <body>
        <div id="__next"></div>
        <script id="__NEXT_DATA__" type="application/json">{next_json}</script>
      </body>
    </html>
    """
    text, title, pricing = strip_html(html)
    assert "Autonomous AI Agent" in text
    assert title == "NextGen AI"
    assert isinstance(pricing, dict)
