"""Basic model tests (no database required)."""
from src.tradescout import models
from src.tradescout.models import CRMStatus


def test_crm_status_values():
    assert CRMStatus.NEW.value == "new"
    assert CRMStatus.WON.value == "won"
    assert CRMStatus.LOST.value == "lost"


def test_campaign_defaults():
    campaign = models.Campaign(name="Test Campaign")
    assert campaign.name == "Test Campaign"
    assert campaign.id is None
    assert campaign.created_at is not None


def test_lead_default_status():
    lead = models.Lead(company_name="ACME", website="https://acme.example.com")
    assert lead.crm_status == CRMStatus.NEW
    assert lead.score == 0.0
    assert lead.id is None


def test_message_requires_content():
    msg = models.Message(lead_id=1, content="Hello there")
    assert msg.content == "Hello there"
    assert msg.channel == "email"
    assert msg.id is None
