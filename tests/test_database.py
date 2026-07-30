"""Database tests: init, seed, read and update (isolated temp SQLite)."""
import os
import tempfile

from sqlmodel import select

from src.tradescout import crm, models
from src.tradescout.db import get_engine, get_session, init_db
from src.tradescout.mock_data import seed_mock_data


def _make_engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # we only want the path; sqlite will create the file
    engine = get_engine(f"sqlite:///{path}")
    init_db(engine)
    return engine, path


def _cleanup(engine, path):
    # Release the pooled connection so Windows lets us delete the file.
    engine.dispose()
    if os.path.exists(path):
        os.remove(path)


def test_init_db_creates_tables():
    engine, path = _make_engine()
    try:
        with get_session(engine) as session:
            session.add(models.Campaign(name="X"))
            session.commit()
        assert True
    finally:
        _cleanup(engine, path)


def test_seed_and_read_leads():
    engine, path = _make_engine()
    try:
        seeded = seed_mock_data(engine)
        assert seeded is True
        leads = crm.get_leads(engine)
        assert len(leads) == 5
        campaigns = crm.get_campaigns(engine)
        assert len(campaigns) == 1
    finally:
        _cleanup(engine, path)


def test_update_lead_status_persists():
    engine, path = _make_engine()
    try:
        seed_mock_data(engine)
        lead = crm.get_leads(engine)[0]
        updated = crm.update_lead_status(engine, lead.id, models.CRMStatus.WON)
        assert updated is not None
        assert updated.crm_status == models.CRMStatus.WON

        # confirm it was persisted, not just changed in memory
        reread = crm.get_leads(engine)[0]
        assert reread.crm_status == models.CRMStatus.WON
    finally:
        _cleanup(engine, path)


def test_update_missing_lead_returns_none():
    engine, path = _make_engine()
    try:
        assert crm.update_lead_status(engine, 999, models.CRMStatus.WON) is None
    finally:
        _cleanup(engine, path)
