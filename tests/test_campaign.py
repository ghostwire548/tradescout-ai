"""Tests for multi-campaign management."""
import os
import tempfile

from src.tradescout import crm, importer, models
from src.tradescout.db import get_engine, get_session, init_db


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


def test_create_campaign_persists():
    engine, path = _make_engine()
    try:
        camp = crm.create_campaign(engine, "Q4 Trade Show", "Frankfurt 2026")
        assert camp.id is not None
        assert camp.name == "Q4 Trade Show"
        campaigns = crm.get_campaigns(engine)
        assert len(campaigns) == 1
        assert campaigns[0].id == camp.id
    finally:
        _cleanup(engine, path)


def test_get_leads_for_campaign_filters_correctly():
    engine, path = _make_engine()
    try:
        c1 = crm.create_campaign(engine, "Camp A")
        c2 = crm.create_campaign(engine, "Camp B")
        with get_session(engine) as s:
            s.add(models.Lead(company_name="A1", campaign_id=c1.id))
            s.add(models.Lead(company_name="A2", campaign_id=c1.id))
            s.add(models.Lead(company_name="B1", campaign_id=c2.id))
            s.commit()

        a = crm.get_leads_for_campaign(engine, c1.id)
        b = crm.get_leads_for_campaign(engine, c2.id)
        assert len(a) == 2
        assert len(b) == 1
        assert {lead.company_name for lead in a} == {"A1", "A2"}
    finally:
        _cleanup(engine, path)


def test_create_campaign_strips_whitespace():
    engine, path = _make_engine()
    try:
        camp = crm.create_campaign(engine, "  Padded Name  ", "  desc  ")
        assert camp.name == "Padded Name"
        assert camp.description == "desc"
    finally:
        _cleanup(engine, path)


def test_commit_import_to_specific_campaign():
    engine, path = _make_engine()
    try:
        c1 = crm.create_campaign(engine, "Target")
        c2 = crm.create_campaign(engine, "Other")
        candidates = [
            importer.Candidate(row_index=0, company_name="Co X"),
            importer.Candidate(row_index=1, company_name="Co Y"),
        ]
        n = importer.commit_import(engine, candidates, campaign_id=c1.id)
        assert n == 2
        assert len(crm.get_leads_for_campaign(engine, c1.id)) == 2
        assert len(crm.get_leads_for_campaign(engine, c2.id)) == 0
    finally:
        _cleanup(engine, path)


def test_commit_import_defaults_to_ensure_default():
    engine, path = _make_engine()
    try:
        candidates = [importer.Candidate(row_index=0, company_name="Defaulted")]
        n = importer.commit_import(engine, candidates)  # no campaign_id given
        assert n == 1
        camps = crm.get_campaigns(engine)
        assert len(camps) == 1
        leads = crm.get_leads_for_campaign(engine, camps[0].id)
        assert len(leads) == 1
    finally:
        _cleanup(engine, path)


def test_empty_campaign_returns_no_leads():
    engine, path = _make_engine()
    try:
        camp = crm.create_campaign(engine, "Empty")
        assert crm.get_leads_for_campaign(engine, camp.id) == []
    finally:
        _cleanup(engine, path)
