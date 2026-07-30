"""Tests for the outreach message generation framework (Milestone: messages)."""
import os
import tempfile

from src.tradescout.db import get_engine, get_session, init_db
from src.tradescout import crm, messaging, models


def _temp_engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # we only want the path; sqlite will create the file
    engine = get_engine(f"sqlite:///{path}")
    init_db(engine)
    return engine, path


def test_template_generator_email():
    lead = models.Lead(
        company_name="Acme",
        website="https://acme.com",
        industry="Machinery",
        country="Germany",
    )
    gen = messaging.generate_message(lead, channel="email")
    assert gen.generator_name == "template"
    assert gen.channel == "email"
    assert gen.subject
    assert gen.content and "Acme" in gen.content


def test_template_generator_all_channels():
    lead = models.Lead(company_name="Acme", industry="Machinery", country="Germany")
    for ch in messaging.SUPPORTED_CHANNELS:
        gen = messaging.generate_message(lead, channel=ch)
        assert gen.content.strip(), f"empty content for channel {ch}"


def test_generate_message_default_active_is_template():
    assert messaging.ACTIVE_GENERATOR is messaging.template_generator
    lead = models.Lead(company_name="Acme")
    gen = messaging.generate_message(lead)
    assert gen.generator_name == "template"


def test_llm_generator_falls_back_to_template():
    """When no LLM API key is set, llm_generator gracefully falls back
    to the offline template generator instead of crashing."""
    lead = models.Lead(company_name="Acme")
    gen = messaging.llm_generator(lead)
    assert gen.generator_name == "template"  # fell back
    assert gen.content and "Acme" in gen.content


def test_swap_active_generator():
    lead = models.Lead(company_name="Acme")
    original = messaging.ACTIVE_GENERATOR
    try:

        def fake(lead, analysis=None, channel="email", language="en"):
            return messaging.GeneratedMessage(
                lead_id=lead.id, channel=channel, content="FAKE", generator_name="fake"
            )

        messaging.ACTIVE_GENERATOR = fake
        gen = messaging.generate_message(lead)
        assert gen.generator_name == "fake"
    finally:
        messaging.ACTIVE_GENERATOR = original  # restore for other tests


def test_to_persist_email_includes_subject():
    gen = messaging.GeneratedMessage(
        lead_id=1, channel="email", content="BODY", subject="SUB", generator_name="template"
    )
    msg = gen.to_persist()
    assert msg.content.startswith("Subject: SUB")
    assert "BODY" in msg.content
    assert msg.channel == "email"


def test_create_and_get_messages():
    engine, path = _temp_engine()
    try:
        with get_session(engine) as s:
            lead = models.Lead(company_name="Acme")
            s.add(lead)
            s.commit()
            s.refresh(lead)
        assert crm.get_messages(engine, lead.id) == []
        crm.create_message(engine, lead.id, "email", "Hello Acme")
        msgs = crm.get_messages(engine, lead.id)
        assert len(msgs) == 1
        assert msgs[0].content == "Hello Acme"
        assert msgs[0].channel == "email"
    finally:
        engine.dispose()
        os.remove(path)


def test_save_message_keeps_lead_count():
    engine, path = _temp_engine()
    try:
        with get_session(engine) as s:
            lead = models.Lead(company_name="Acme")
            s.add(lead)
            s.commit()
            s.refresh(lead)
        leads_before = len(crm.get_leads(engine))
        crm.create_message(engine, lead.id, "email", "x")
        assert len(crm.get_leads(engine)) == leads_before
    finally:
        engine.dispose()
        os.remove(path)
