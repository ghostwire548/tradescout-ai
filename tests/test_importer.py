"""Unit tests for the CSV Lead import pipeline (no UI required).

Covers normalization, header auto-mapping, dedup (domain + name/phone
fallback), preview classification and transactional commit that never
corrupts existing data.
"""
import csv
import io
import os
import tempfile

import pytest

from src.tradescout import crm, importer, models
from src.tradescout.db import get_engine, get_session, init_db
from src.tradescout.mock_data import seed_mock_data


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _make_engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    engine = get_engine(f"sqlite:///{path}")
    init_db(engine)
    return engine, path


def _cleanup(engine, path):
    engine.dispose()
    if os.path.exists(path):
        os.remove(path)


def _csv_bytes(headers, rows, encoding="utf-8") -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode(encoding)


# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #
def test_normalize_company_name():
    assert importer.normalize_company_name("  ACME   Corp ") == "ACME Corp"
    assert importer.normalize_company_name(None) == ""
    assert importer.normalize_company_name("") == ""


def test_normalize_domain():
    assert importer.normalize_domain("https://WWW.Example.com/about") == "example.com"
    assert importer.normalize_domain("Example.com") == "example.com"
    assert importer.normalize_domain("http://www.foo.com/") == "foo.com"
    assert importer.normalize_domain("") is None
    assert importer.normalize_domain(None) is None


def test_normalize_phone():
    assert importer.normalize_phone("+1 (415) 555-2671") == "+14155552671"
    assert importer.normalize_phone("415-555-2671") == "4155552671"
    assert importer.normalize_phone("  ") is None
    assert importer.normalize_phone("abc") is None


def test_normalize_email():
    assert importer.normalize_email("  Foo@Bar.COM ") == "foo@bar.com"
    assert importer.normalize_email(None) is None


# --------------------------------------------------------------------------- #
# Header auto-mapping
# --------------------------------------------------------------------------- #
def test_suggest_mapping_english():
    headers = ["Company", "URL", "Tel", "Email", "Industry"]
    m = importer.suggest_mapping(headers)
    assert m["company_name"] == "Company"
    assert m["website"] == "URL"
    assert m["phone"] == "Tel"
    assert m["email"] == "Email"
    assert m["category"] == "Industry"


def test_suggest_mapping_chinese_gbk():
    headers = ["公司", "网址"]
    data = _csv_bytes(headers, [["北京贸易有限公司", "https://bj.example.com"]], encoding="gbk")
    parsed = importer.read_csv_headers(data)
    m = importer.suggest_mapping(parsed)
    assert m["company_name"] == "公司"
    assert m["website"] == "网址"


# --------------------------------------------------------------------------- #
# Preview classification + dedup
# --------------------------------------------------------------------------- #
def test_analyze_csv_classifies_new_duplicate_invalid():
    engine, path = _make_engine()
    try:
        seed_mock_data(engine)
        # An existing lead with NO website but name + phone (fallback dedup).
        with get_session(engine) as session:
            session.add(models.Lead(company_name="No Web Co", phone="123456",
                                     campaign_id=1))
            session.commit()

        headers = ["Company", "Website", "Phone"]
        rows = [
            ["New Co", "https://newco.example.com", ""],            # new
            ["Dup IKEA", "ikea.com", ""],                           # dup by domain
            ["", "", ""],                                          # invalid (no name)
            ["No Web Co", "", "123456"],                           # dup by name+phone
        ]
        data = _csv_bytes(headers, rows)
        mapping = {"company_name": "Company", "website": "Website", "phone": "Phone"}
        pv = importer.analyze_csv(engine, data, mapping)

        assert pv.new_count == 1
        assert pv.duplicate_count == 2
        assert pv.invalid_count == 1
        assert len(pv.new_candidates) == 1
        assert pv.new_candidates[0].company_name == "New Co"
    finally:
        _cleanup(engine, path)


def test_analyze_csv_gbk_chinese_values():
    engine, path = _make_engine()
    try:
        seed_mock_data(engine)
        headers = ["公司", "网址"]
        rows = [["北京贸易有限公司", "https://bj.example.com"]]
        data = _csv_bytes(headers, rows, encoding="gbk")
        mapping = importer.suggest_mapping(importer.read_csv_headers(data))
        pv = importer.analyze_csv(engine, data, mapping)
        assert pv.new_count == 1
        assert pv.new_candidates[0].company_name == "北京贸易有限公司"
    finally:
        _cleanup(engine, path)


# --------------------------------------------------------------------------- #
# Commit (transactional, non-destructive)
# --------------------------------------------------------------------------- #
def test_commit_import_inserts_only_new_and_preserves_existing():
    engine, path = _make_engine()
    try:
        seed_mock_data(engine)
        with get_session(engine) as session:
            session.add(models.Lead(company_name="No Web Co", phone="123456",
                                     campaign_id=1))
            session.commit()
        before = len(crm.get_leads(engine))

        headers = ["Company", "Website", "Phone"]
        rows = [
            ["New Co", "https://newco.example.com", ""],
            ["Dup IKEA", "ikea.com", ""],
            ["", "", ""],
            ["No Web Co", "", "123456"],
        ]
        data = _csv_bytes(headers, rows)
        mapping = {"company_name": "Company", "website": "Website", "phone": "Phone"}
        pv = importer.analyze_csv(engine, data, mapping)

        n = importer.commit_import(engine, pv.new_candidates)
        assert n == 1
        after = crm.get_leads(engine)
        assert len(after) == before + 1

        # existing data untouched
        names = {lead.company_name for lead in after}
        assert "IKEA" in names             # original mock lead
        assert "No Web Co" in names             # original fallback lead
    finally:
        _cleanup(engine, path)


def test_commit_import_empty_is_noop():
    engine, path = _make_engine()
    try:
        seed_mock_data(engine)
        before = len(crm.get_leads(engine))
        assert importer.commit_import(engine, []) == 0
        assert len(crm.get_leads(engine)) == before
    finally:
        _cleanup(engine, path)


def test_committed_lead_has_mapped_fields():
    engine, path = _make_engine()
    try:
        seed_mock_data(engine)
        headers = ["Company", "Website", "Phone", "Email", "Industry", "City"]
        rows = [["Acme Ltd", "https://acme.example.com", "+86 21 6666 8888",
                 "Sales@Acme.com", "Machinery", "Shanghai"]]
        data = _csv_bytes(headers, rows)
        mapping = importer.suggest_mapping(importer.read_csv_headers(data))
        pv = importer.analyze_csv(engine, data, mapping)
        importer.commit_import(engine, pv.new_candidates)

        lead = next(l for l in crm.get_leads(engine) if l.company_name == "Acme Ltd")
        assert lead.website == "acme.example.com"
        assert lead.phone == "+862166668888"
        assert lead.contact_email == "sales@acme.com"
        assert lead.industry == "Machinery"
        assert lead.city == "Shanghai"
        assert lead.crm_status == models.CRMStatus.NEW
    finally:
        _cleanup(engine, path)
