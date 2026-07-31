"""Outreach message generation (Milestone: Message generation).

Framework with a swappable generator. The default generator is an OFFLINE
template engine (no API key, no network). A reserved ``llm_generator`` interface
is provided so later milestones can plug in an LLM without changing any caller.

To switch engines later (once a key/backend exists):
    import messaging
    messaging.ACTIVE_GENERATOR = messaging.llm_generator
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from . import models


# Channels offered in the UI. The Message.channel column is free-text, so this
# list can be extended without any schema change.
SUPPORTED_CHANNELS = ["email", "linkedin", "whatsapp"]

DEFAULT_LANGUAGE = "en"


@dataclass
class GeneratedMessage:
    """Result of a generation pass, ready to persist or display."""

    lead_id: int
    channel: str
    content: str
    generator_name: str
    subject: str = ""

    def to_persist(self) -> models.Message:
        """Build a Message row from this result.

        For email we prepend the subject so the saved record is self-contained.
        """
        content = self.content
        if self.subject and self.channel == "email":
            content = f"Subject: {self.subject}\n\n{self.content}"
        return models.Message(
            lead_id=self.lead_id,
            channel=self.channel,
            content=content,
        )


# --- Offline template generator (ACTIVE default) --------------------------

def _safe(value: Optional[str], placeholder: str = "your company") -> str:
    return (value or "").strip() or placeholder


def template_generator(
    lead: models.Lead,
    analysis: Optional[models.WebsiteAnalysis] = None,
    channel: str = "email",
    language: str = DEFAULT_LANGUAGE,
) -> GeneratedMessage:
    """Deterministic, offline template-based message generator.

    Composes a B2B outreach draft from local lead fields (and optionally a
    prior website analysis). No network, no API key.
    """
    company = _safe(lead.company_name, "your company")
    industry = _safe(lead.industry, "your industry")
    country = _safe(lead.country, "your market")
    website = _safe(lead.website, "your website")

    tech_signal = ""
    if analysis is not None and analysis.status == models.AnalysisStatus.DONE:
        techs = analysis.technologies_list
        if techs:
            tech_signal = f" I noticed you work with {', '.join(techs[:3])}."

    # English B2B outreach (foreign-trade context); easy to localize later.
    if channel == "email":
        subject = f"Partnership opportunity for {company} ({industry})"
        body = (
            f"Hi {company} team,\n\n"
            f"I came across {website} and was impressed by what you do in the "
            f"{industry} space.{tech_signal}\n\n"
            f"We help {industry} companies in {country} streamline sourcing and "
            f"grow export pipelines with verified leads and tailored outreach.\n\n"
            f"Would you be open to a short call next week to explore if there's a fit?\n\n"
            f"Best regards,\n[Your Name]\n[Your Company]"
        )
    elif channel == "linkedin":
        body = (
            f"Hi {company} team — loved what you're building in {industry}. "
            f"We help {industry} exporters in {country} find verified buyers. "
            f"Open to connecting?"
        )
        subject = ""
    elif channel == "whatsapp":
        body = (
            f"Hi {company}! We help {industry} companies in {country} get "
            f"verified export leads. Interested in a quick chat?"
        )
        subject = ""
    else:
        body = f"Hi {company}, we'd love to explore a partnership in {industry}."
        subject = ""

    return GeneratedMessage(
        lead_id=lead.id,
        channel=channel,
        content=body,
        subject=subject,
        generator_name="template",
    )


# --- LLM generator ---------------------------------------------------------

def _build_llm_prompt(
    lead: models.Lead,
    analysis: Optional[models.WebsiteAnalysis],
    channel: str,
) -> list[dict]:
    """Build a system + user prompt for the LLM."""
    company = lead.company_name
    industry = lead.industry or "N/A"
    country = lead.country or "N/A"
    website = lead.website or ""

    analysis_text = ""
    if analysis and analysis.status == models.AnalysisStatus.DONE and analysis.summary:
        analysis_text = f"\n网站分析摘要：{analysis.summary}"

    channel_guide = {
        "email": "写一封正式但友好的 B2B 开发邮件，包含主题行（Subject: ...）和正文。邮件应简短有力，不超过 150 个英文词。",
        "linkedin": "写一段简短的 LinkedIn InMail 或连接请求附言，不超过 300 字符。语气专业但亲和。",
        "whatsapp": "写一段简短的 WhatsApp 开场消息，不超过 200 字符。语气轻松友好。",
    }

    system = (
        "你是一位资深的外贸 B2B 开发专家。根据客户信息写个性化开发话术。"
        "话术应专业、简洁、有针对性，避免空洞的套话。"
        f"目标渠道：{channel}。{channel_guide.get(channel, '')}"
    )
    user = (
        f"公司：{company}\n行业：{industry}\n国家/地区：{country}\n"
        f"网站：{website}{analysis_text}\n\n"
        f"请为上述客户生成 {channel} 渠道的开发话术。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def llm_generator(
    lead: models.Lead,
    analysis: Optional[models.WebsiteAnalysis] = None,
    channel: str = "email",
    language: str = DEFAULT_LANGUAGE,
) -> GeneratedMessage:
    """LLM-powered outreach generator.

    Calls the configured LLM (OpenAI-compatible). Falls back to
    ``template_generator`` if no API key is set or the call fails.
    """
    from .llm import chat  # deferred import to avoid circular dep

    messages = _build_llm_prompt(lead, analysis, channel)
    result = chat(messages, temperature=0.7, max_tokens=800)
    if result is not None:
        subject = ""
        if channel == "email" and result.lower().startswith("subject:"):
            lines = result.split("\n", 1)
            subject = lines[0].replace("Subject:", "").strip()
            result = lines[1].strip() if len(lines) > 1 else result
        return GeneratedMessage(
            lead_id=lead.id,
            channel=channel,
            content=result,
            subject=subject,
            generator_name="llm",
        )
    # Fall back to offline template on any LLM failure / missing key.
    return template_generator(lead, analysis=analysis, channel=channel, language=language)


# Auto-select the active generator at import time.
from .llm import is_available as _llm_avail  # noqa: E402

ACTIVE_GENERATOR: Callable[..., GeneratedMessage] = (
    llm_generator if _llm_avail() else template_generator
)


def generate_message(
    lead: models.Lead,
    analysis: Optional[models.WebsiteAnalysis] = None,
    channel: str = "email",
    language: str = DEFAULT_LANGUAGE,
) -> GeneratedMessage:
    """Generate an outreach message for a lead using the active generator."""
    return ACTIVE_GENERATOR(lead, analysis=analysis, channel=channel, language=language)
