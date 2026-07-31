"""Mock data generator - no API keys required.

Provides 5 realistic B2B leads plus a demo campaign so the workbench is
usable out of the box in ``mock_mode``.
"""
from __future__ import annotations

from sqlmodel import select

from . import models
from .config import settings
from .db import get_session


def get_mock_leads() -> list[models.Lead]:
    """5 real B2B-relevant companies with live websites — analysis pipeline
    produces actual results out of the box (no more example.com stubs)."""
    return [
        models.Lead(
            company_name="IKEA",
            website="ikea.com",
            industry="Furniture & Home",
            country="Sweden",
            contact_email="supplier@ikea.com",
            score=85.0,
            crm_status=models.CRMStatus.QUALIFIED,
        ),
        models.Lead(
            company_name="DJI",
            website="dji.com",
            industry="Electronics & Drones",
            country="China",
            contact_email="enterprise@dji.com",
            score=78.0,
            crm_status=models.CRMStatus.CONTACTED,
        ),
        models.Lead(
            company_name="Siemens",
            website="siemens.com",
            industry="Industrial Machinery & Automation",
            country="Germany",
            contact_email="industry@siemens.com",
            score=92.0,
            crm_status=models.CRMStatus.NEW,
        ),
        models.Lead(
            company_name="Patagonia",
            website="patagonia.com",
            industry="Textiles & Outdoor Apparel",
            country="USA",
            contact_email="wholesale@patagonia.com",
            score=70.0,
            crm_status=models.CRMStatus.NEGOTIATION,
        ),
        models.Lead(
            company_name="Natura & Co",
            website="natura.com.br",
            industry="Cosmetics & Personal Care",
            country="Brazil",
            contact_email="export@natura.net",
            score=62.0,
            crm_status=models.CRMStatus.LOST,
        ),
    ]


def seed_mock_data(engine, force: bool = False) -> bool:
    """Insert a demo campaign + 5 mock leads if the DB is empty.

    Returns ``True`` when data was seeded, ``False`` when data already exists.
    """
    with get_session(engine) as session:
        existing = session.exec(select(models.Lead)).first()
        if existing and not force:
            return False

        if force:
            for lead in session.exec(select(models.Lead)).all():
                session.delete(lead)
            for campaign in session.exec(select(models.Campaign)).all():
                session.delete(campaign)
            session.commit()

        campaign = models.Campaign(
            name=settings.default_campaign_name,
            description="Auto-generated demo campaign (mock mode, no API key required).",
        )
        session.add(campaign)
        session.commit()
        session.refresh(campaign)

        for lead in get_mock_leads():
            lead.campaign_id = campaign.id
            session.add(lead)
        session.commit()
    return True
