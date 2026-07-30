"""CRM operations: read leads/campaigns and update lead CRM status + score.

Milestone 0: CRM status. Milestone 1: score updates (driven by the scoring
framework). Milestone (Campaigns): multi-campaign CRUD.
"""
from __future__ import annotations

from sqlmodel import select

from . import models
from .config import settings
from .db import get_session


def get_campaigns(engine) -> list[models.Campaign]:
    with get_session(engine) as session:
        stmt = select(models.Campaign).order_by(models.Campaign.created_at.desc())
        return list(session.exec(stmt).all())


def create_campaign(engine, name: str, description: str = "") -> models.Campaign:
    """Create a new campaign and return it. Name must be non-empty."""
    with get_session(engine) as session:
        campaign = models.Campaign(name=name.strip(), description=description.strip())
        session.add(campaign)
        session.commit()
        session.refresh(campaign)
        return campaign


def get_leads_for_campaign(engine, campaign_id: int) -> list[models.Lead]:
    """Return leads belonging to a specific campaign, newest first."""
    with get_session(engine) as session:
        return list(
            session.exec(
                select(models.Lead)
                .where(models.Lead.campaign_id == campaign_id)
                .order_by(models.Lead.created_at.desc())
            ).all()
        )


def ensure_default_campaign(engine) -> int:
    """Return the id of the first campaign, creating a default one if none exist.

    Imported leads are attached to this campaign so they always have a valid
    foreign key.
    """
    with get_session(engine) as session:
        campaign = session.exec(select(models.Campaign)).first()
        if campaign is not None:
            return campaign.id
        campaign = models.Campaign(
            name=settings.default_campaign_name,
            description="Default campaign for imported leads.",
        )
        session.add(campaign)
        session.commit()
        session.refresh(campaign)
        return campaign.id


def get_leads(engine) -> list[models.Lead]:
    with get_session(engine) as session:
        return list(session.exec(select(models.Lead)).all())


def get_lead(engine, lead_id: int) -> models.Lead | None:
    with get_session(engine) as session:
        return session.get(models.Lead, lead_id)


def update_lead_status(engine, lead_id: int, status: models.CRMStatus) -> models.Lead | None:
    """Persist a new CRM status for a lead. Returns the lead or None if missing."""
    with get_session(engine) as session:
        lead = session.get(models.Lead, lead_id)
        if lead is None:
            return None
        lead.crm_status = status
        session.add(lead)
        session.commit()
        session.refresh(lead)
        return lead


def update_lead_score(engine, lead_id: int, score: float) -> models.Lead | None:
    """Persist a recomputed CRM score for a lead. Returns the lead or None."""
    with get_session(engine) as session:
        lead = session.get(models.Lead, lead_id)
        if lead is None:
            return None
        lead.score = score
        session.add(lead)
        session.commit()
        session.refresh(lead)
        return lead


def get_messages(engine, lead_id: int) -> list[models.Message]:
    """Return all saved outreach messages for a lead (oldest first)."""
    with get_session(engine) as session:
        return list(
            session.exec(
                select(models.Message).where(models.Message.lead_id == lead_id)
            ).all()
        )


def create_message(
    engine, lead_id: int, channel: str, content: str
) -> models.Message:
    """Persist a generated outreach message for a lead. Returns the new row."""
    with get_session(engine) as session:
        msg = models.Message(lead_id=lead_id, channel=channel, content=content)
        session.add(msg)
        session.commit()
        session.refresh(msg)
        return msg

