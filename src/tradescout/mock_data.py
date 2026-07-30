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
    return [
        models.Lead(
            company_name="Nordic Woodcraft AB",
            website="https://nordicwoodcraft.example.com",
            industry="Furniture Manufacturing",
            country="Sweden",
            contact_email="sales@nordicwoodcraft.example.com",
            score=82.5,
            crm_status=models.CRMStatus.QUALIFIED,
        ),
        models.Lead(
            company_name="Shenzhen BrightLED Co., Ltd.",
            website="https://brightled.example.com",
            industry="LED Lighting",
            country="China",
            contact_email="info@brightled.example.com",
            score=76.0,
            crm_status=models.CRMStatus.CONTACTED,
        ),
        models.Lead(
            company_name="Bayern Precision GmbH",
            website="https://bayernprecision.example.com",
            industry="Industrial Machinery",
            country="Germany",
            contact_email="contact@bayernprecision.example.com",
            score=91.2,
            crm_status=models.CRMStatus.NEW,
        ),
        models.Lead(
            company_name="Pacific Organic Foods Inc.",
            website="https://pacificorganic.example.com",
            industry="Food & Beverage",
            country="USA",
            contact_email="hello@pacificorganic.example.com",
            score=68.4,
            crm_status=models.CRMStatus.NEGOTIATION,
        ),
        models.Lead(
            company_name="Mercosur Textiles LTDA",
            website="https://mercosurtextiles.example.com",
            industry="Textiles & Apparel",
            country="Brazil",
            contact_email="export@mercosurtextiles.example.com",
            score=59.7,
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
