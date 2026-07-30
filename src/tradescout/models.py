"""SQLModel data models: Campaign, Lead, Message.

Milestone 0 defines the three base entities. Relationships are declared for
future milestones but are not required by the current UI.
"""
import json
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from sqlmodel import SQLModel, Field, Relationship


class CRMStatus(str, Enum):
    """Lifecycle status of a lead inside the local CRM."""

    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Campaign(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)

    leads: List["Lead"] = Relationship(back_populates="campaign")


class Lead(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: Optional[int] = Field(default=None, foreign_key="campaign.id")
    company_name: str = Field(index=True)
    website: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    score: float = Field(default=0.0)
    crm_status: CRMStatus = Field(default=CRMStatus.NEW)
    created_at: datetime = Field(default_factory=_utcnow)

    campaign: Optional[Campaign] = Relationship(back_populates="leads")
    messages: List["Message"] = Relationship(back_populates="lead")
    analyses: List["WebsiteAnalysis"] = Relationship(back_populates="lead")


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")
    channel: str = "email"
    content: str
    created_at: datetime = Field(default_factory=_utcnow)

    lead: Optional[Lead] = Relationship(back_populates="messages")


class AnalysisStatus(str, Enum):
    """Status of a website analysis job."""

    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    ERROR = "error"


class WebsiteAnalysis(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")
    url: str = ""
    status: AnalysisStatus = Field(default=AnalysisStatus.PENDING)
    summary: Optional[str] = None
    technologies: str = "[]"  # JSON array string, e.g. '["Shopify", "Cloudflare"]'
    analysis_score_signal: float = 0.0
    raw_excerpt: Optional[str] = None
    error: Optional[str] = None
    analyzed_at: datetime = Field(default_factory=_utcnow)

    lead: Optional[Lead] = Relationship(back_populates="analyses")

    @property
    def technologies_list(self) -> list[str]:
        try:
            return json.loads(self.technologies or "[]")
        except (json.JSONDecodeError, TypeError):
            return []
