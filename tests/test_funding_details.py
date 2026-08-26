from scanner.fetch_articles import parse_details_text

HEADING_VARIANT = """Company Website:
https://tryarc.com
Company:
Arc
Raised:
$10.76M
Round:
Seed
Funding Date:
May 26, 2026
Lead Investor:
Andreessen Horowitz
Additional Investors:
Adverb Ventures, Broadway Restaurant Group, LLC
Software Category:
Voice AI
Source:
https://example.com/press"""

BODY_VARIANT = """Some intro paragraph text.
Company:
Mistral AI
Raised:
$113.0M
Round:
Seed Round
Funding Month:
June 2023
Lead Investors:
Lightspeed Venture Partners
Additional Investors:
Xavier Niel, JCDecaux Holding
Company Website: https://mistral.ai/
Software Category:
Open Source Solutions
About the Company: Founded in Paris.
Source:
https://techcrunch.example/mistral
by
Ben Murray"""


def test_heading_variant():
    d = parse_details_text(HEADING_VARIANT)
    assert d["company"] == "Arc"
    assert d["website"] == "https://tryarc.com"
    assert d["raised"] == "$10.76M"
    assert d["round"] == "Seed"
    assert d["funding_date"] == "May 26, 2026"
    assert d["lead_investor"] == "Andreessen Horowitz"
    assert d["additional_investors"] == "Adverb Ventures, Broadway Restaurant Group, LLC"
    assert d["software_category"] == "Voice AI"
    assert d["source"] == "https://example.com/press"


def test_body_variant_with_plural_and_inline():
    d = parse_details_text(BODY_VARIANT)
    assert d["company"] == "Mistral AI"
    assert d["raised"] == "$113.0M"
    assert d["round"] == "Seed Round"
    assert d["funding_date"] == "June 2023"  # Funding Month alias
    assert d["lead_investor"] == "Lightspeed Venture Partners"  # plural alias
    assert d["additional_investors"] == "Xavier Niel, JCDecaux Holding"
    assert d["website"] == "https://mistral.ai/"  # inline value
    assert d["software_category"] == "Open Source Solutions"
    assert d["source"] == "https://techcrunch.example/mistral"


def test_company_label_does_not_shadow_website():
    d = parse_details_text("Company:\nAcme\nCompany Website:\nhttps://acme.io")
    assert d["company"] == "Acme"
    assert d["website"] == "https://acme.io"


def test_empty_additional_investors():
    d = parse_details_text(
        "Additional Investors:\nCompany Website: https://tranch.com/\nSoftware Category: BNPL"
    )
    assert d["additional_investors"] == ""
    assert d["website"] == "https://tranch.com/"
    assert d["software_category"] == "BNPL"
