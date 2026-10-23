from scanner.enrich import enrich_companies, enrich_company, update_site


def test_enrich_company_joins_site_pricing_and_status():
    company = {"slug": "acme", "domain": "acme.io", "company": "Acme"}
    sites = {
        "acme.io": {
            "status": "ok",
            "pricing": {"summary": "Starter $49/mo", "has_public_pricing": True},
        }
    }

    enriched = enrich_company(company, sites)

    assert enriched["site_status"] == "ok"
    assert enriched["pricing"]["summary"] == "Starter $49/mo"
    assert company == {"slug": "acme", "domain": "acme.io", "company": "Acme"}


def test_enrich_company_without_site_is_a_copy():
    company = {"slug": "acme", "domain": "missing.io"}

    enriched = enrich_company(company, {})

    assert enriched == company
    assert enriched is not company


def test_enrich_companies_keeps_order_and_handles_missing_domains():
    companies = [
        {"slug": "a", "domain": "a.io"},
        {"slug": "b"},
        {"slug": "c", "domain": "c.io"},
    ]
    sites = {"a.io": {"status": "ok", "pricing": {}}}

    enriched = enrich_companies(companies, sites)

    assert [c["slug"] for c in enriched] == ["a", "b", "c"]
    assert enriched[0]["site_status"] == "ok"
    assert "site_status" not in enriched[1]
    assert "site_status" not in enriched[2]


def test_update_site_merges_without_dropping_other_domains(tmp_path):
    path = tmp_path / "sites.json"
    update_site("a.io", {"domain": "a.io", "status": "ok"}, path=path)
    update_site("b.io", {"domain": "b.io", "status": "dead"}, path=path)
    update_site("a.io", {"domain": "a.io", "status": "js_only"}, path=path)

    from scanner.storage import read_json

    sites = read_json(path)["sites"]
    assert set(sites) == {"a.io", "b.io"}
    assert sites["a.io"]["status"] == "js_only"
    assert sites["b.io"]["status"] == "dead"
