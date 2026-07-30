"""Lead scoring framework (Milestone 1 - framework + reserved interface).

Provides a deterministic heuristic scorer (0-100) plus a swappable scorer
registry so an LLM-based scorer can be dropped in later without changing
callers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from . import models

# Illustrative country tier -> base points. Keys are lower-cased so lookups
# are case-insensitive (e.g. "USA", "usa" and "Usa" all match).
_COUNTRY_TIER: dict[str, float] = {
    k.lower(): v
    for k, v in {
        "USA": 20.0,
        "Germany": 18.0,
        "Sweden": 16.0,
        "China": 14.0,
        "Brazil": 12.0,
    }.items()
}
_DEFAULT_COUNTRY_POINTS = 8.0

# Weights sum to 100.
_WEIGHTS = {
    "website": 20.0,
    "email": 10.0,
    "industry": 10.0,
    "country": 20.0,
    "analysis_signal": 40.0,
}


@dataclass
class ScoreResult:
    total: float
    factors: dict[str, float] = field(default_factory=dict)


ScorerFn = Callable[[models.Lead, Optional[models.WebsiteAnalysis]], ScoreResult]


def default_scorer(
    lead: models.Lead, analysis: Optional[models.WebsiteAnalysis] = None
) -> ScoreResult:
    """Heuristic scorer (0-100).

    TODO: replace with an LLM scorer if desired - keep the same signature and
    assign ``ACTIVE_SCORER`` to it.
    """
    factors: dict[str, float] = {}

    factors["website"] = _WEIGHTS["website"] if lead.website else 0.0
    factors["email"] = _WEIGHTS["email"] if lead.contact_email else 0.0
    factors["industry"] = _WEIGHTS["industry"] if lead.industry else 0.0
    # Normalize case before lookup so CSV values like "usa"/"germany" match.
    factors["country"] = _COUNTRY_TIER.get(
        (lead.country or "").strip().lower(), _DEFAULT_COUNTRY_POINTS
    )

    signal = (
        analysis.analysis_score_signal
        if (analysis and analysis.status == models.AnalysisStatus.DONE)
        else 0.0
    )
    # signal already lives on a 0..40 scale
    factors["analysis_signal"] = max(0.0, min(float(signal), _WEIGHTS["analysis_signal"]))

    total = round(sum(factors.values()), 1)
    return ScoreResult(total=total, factors=factors)


# --- LLM scorer ------------------------------------------------------------

def llm_scorer(
    lead: models.Lead, analysis: Optional[models.WebsiteAnalysis] = None
) -> ScoreResult:
    """LLM-assisted lead scorer. Blends the heuristic baseline with an LLM
    qualitative signal (0-40). Falls back to ``default_scorer`` if no API key
    or the LLM call fails.
    """
    from .llm import chat

    base = default_scorer(lead, analysis)
    analysis_text = ""
    if analysis and analysis.status == models.AnalysisStatus.DONE and analysis.summary:
        analysis_text = f"\n网站分析：{analysis.summary}"

    messages = [
        {
            "role": "system",
            "content": (
                "你是一位 B2B 外贸线索评估专家。根据给定的公司信息和网站分析结果，"
                "评估该线索的质量，返回一个 0 到 40 的分数。仅返回数字，不要其他文字。"
                "评分依据：网站质量、公司规模信号、行业匹配度、国际化程度。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"公司：{lead.company_name}\n"
                f"行业：{lead.industry or 'N/A'}\n"
                f"国家：{lead.country or 'N/A'}\n"
                f"网站：{lead.website or '无'}\n"
                f"邮箱：{lead.contact_email or '无'}"
                f"{analysis_text}"
            ),
        },
    ]
    result = chat(messages, temperature=0.3, max_tokens=50)
    if result is not None:
        try:
            llm_signal = float(result.strip())
            llm_signal = max(0.0, min(llm_signal, _WEIGHTS["analysis_signal"]))
        except (ValueError, TypeError):
            llm_signal = base.factors.get("analysis_signal", 0.0)
    else:
        llm_signal = base.factors.get("analysis_signal", 0.0)

    factors = dict(base.factors)
    factors["analysis_signal"] = llm_signal
    total = round(sum(factors.values()), 1)
    return ScoreResult(total=total, factors=factors)


# Auto-select at import time.
from .llm import is_available as _llm_scoring_avail  # noqa: E402

ACTIVE_SCORER: ScorerFn = llm_scorer if _llm_scoring_avail() else default_scorer


def compute_score(
    lead: models.Lead, analysis: Optional[models.WebsiteAnalysis] = None
) -> ScoreResult:
    """Entry point used by the UI / workflows. Honors the active scorer."""
    return ACTIVE_SCORER(lead, analysis)
