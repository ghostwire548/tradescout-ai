"""Website analysis framework.

Real HTTP fetching (no API key, requests-only) + heuristic HTML analysis.
The LLM analyzer is still reserved as a swappable interface for future milestones.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

import requests
from sqlmodel import select

from . import crm, models, scoring
from .db import get_session

# --------------------------------------------------------------------------- #
# Real HTTP fetcher (no API key, uses requests)
# --------------------------------------------------------------------------- #
_FETCH_TIMEOUT = 10
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _default_fetcher(url: str) -> str:
    """Fetch a website's HTML via HTTP GET. Returns page text on success.

    Raises ``requests.RequestException`` (or a subclass) on any fetch error
    so the caller can record an ERROR status in the DB.
    """
    if not url:
        raise ValueError("empty URL")
    # Auto-prepend https:// if no scheme present.
    if not re.match(r"^https?://", url):
        url = f"https://{url}"
    resp = requests.get(
        url,
        timeout=_FETCH_TIMEOUT,
        headers={"User-Agent": _USER_AGENT},
        allow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


# --------------------------------------------------------------------------- #
# Heuristic analyzer (no LLM, regex-based)
# --------------------------------------------------------------------------- #
# Common signals in page source to detect known platforms / tools.
_TECH_SIGNATURES = {
    "Shopify": r"cdn\.shopify\.com|myshopify\.com|Shopify\.shop",
    "WordPress": r"wp-content|wp-includes|wordpress\.org",
    "WooCommerce": r"woocommerce|wc-cart-fragments",
    "Wix": r"static\.wixstatic\.com|wix\.com",
    "Squarespace": r"squarespace\.com|static1\.squarespace\.com",
    "Magento": r"magento|Mage\.|Magento_",
    "Google Analytics": r"google-analytics\.com|gtag\(",
    "Cloudflare": r"cloudflare|__cf",
    "React": r'react\.[a-z]+\.js|__REACT_DEVTOOLS',
    "Vue.js": r'vue\.[a-z]+\.js|__vue__|data-v-',
    "jQuery": r'jquery[a-z0-9.\-]*\.js',
    "Bootstrap": r'bootstrap[a-z0-9.\-]*\.(js|css)',
    "Tailwind CSS": r'tailwindcss|tailwind\.config',
}


def _extract_title(html: str) -> Optional[str]:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        return re.sub(r"\s+", " ", m.group(1).strip())
    return None


def _extract_meta_description(html: str) -> Optional[str]:
    m = re.search(
        r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
        html, re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    return None


def _detect_technologies(html: str) -> list[str]:
    found: list[str] = []
    for name, pattern in _TECH_SIGNATURES.items():
        if re.search(pattern, html, re.IGNORECASE):
            found.append(name)
    return found


def _default_analyzer(html: str, lead: models.Lead) -> dict:
    """Heuristic HTML analyzer: title, meta desc, tech detection, signal 0-40.

    No LLM, no API key. Still swappable via the ``analyzer`` param later.
    """
    html = html or ""
    title = _extract_title(html)
    meta = _extract_meta_description(html)
    technologies = _detect_technologies(html)

    # Signal calculation (0-40)
    signal = 0.0
    if title:
        signal += 10.0
    if meta:
        signal += 10.0
    if technologies:
        signal += min(len(technologies) * 5.0, 15.0)  # cap at 15
    if len(html) > 2000:
        signal += 5.0  # substantial page = moderate signal boost

    # Human-readable summary
    parts: list[str] = []
    if lead.website:
        parts.append(f"已分析 {lead.website}")
    if title:
        parts.append(f"页面标题：{title}")
    if meta:
        parts.append(f"描述：{meta[:120]}")
    if technologies:
        parts.append(f"检测到技术栈：{', '.join(technologies)}")
    if not parts:
        parts.append(f"未能从 {lead.company_name} 官网提取到有效内容")
    summary = "。".join(parts) + "。"

    return {
        "summary": summary,
        "technologies": technologies,
        "signal": signal,
    }


def _llm_analyzer(html: str, lead: models.Lead) -> dict:
    """LLM-powered website analyzer. Falls back to the heuristic on any error
    or if no API key is configured.
    """
    from .llm import chat

    # Keep heuristic results as a baseline / fallback.
    base = _default_analyzer(html, lead)

    # Truncate HTML to avoid token overload (most interesting content is
    # in the first ~4000 chars of text).
    snippet = (html or "")[:6000]
    messages = [
        {
            "role": "system",
            "content": (
                "你是一位 B2B 网站分析专家。根据给定的 HTML 片段简要分析这家公司，"
                "回答两个问题：\n"
                "1. 这家公司是做什么的？（用一句中文概括，不超过 80 字）\n"
                "2. 线索质量信号是多少？（0-40 的整数，基于网站专业度、公司规模迹象、"
                "国际化程度；仅返回数字）\n\n"
                "请按以下格式返回：\n"
                "摘要：<一句话描述>\n"
                "信号：<0-40 的数字>"
            ),
        },
        {"role": "user", "content": f"HTML 片段：\n{snippet}"},
    ]
    result = chat(messages, temperature=0.3, max_tokens=250)
    if result is None:
        return base

    # Parse the LLM response for summary and signal.
    llm_signal = base["signal"]
    llm_summary = base["summary"]
    for line in result.split("\n"):
        line = line.strip()
        if line.startswith("摘要：") or line.startswith("摘要:"):
            llm_summary = line.split("：", 1)[-1].split(":", 1)[-1].strip()
        elif line.startswith("信号：") or line.startswith("信号:"):
            try:
                val = float(line.split("：", 1)[-1].split(":", 1)[-1].strip())
                llm_signal = max(0.0, min(val, 40.0))
            except (ValueError, IndexError):
                pass

    return {
        "summary": llm_summary,
        "technologies": base["technologies"],
        "signal": llm_signal,
    }


# Auto-select the default analyzer at import time.
from .llm import is_available as _llm_analysis_avail  # noqa: E402

_default_analyzer_fn: AnalyzerFn = (
    _llm_analyzer if _llm_analysis_avail() else _default_analyzer
)


# --------------------------------------------------------------------------- #
# Type aliases and queries
# --------------------------------------------------------------------------- #
FetcherFn = Callable[[str], str]
AnalyzerFn = Callable[[str, models.Lead], dict]


def get_latest_analysis(engine, lead_id: int) -> Optional[models.WebsiteAnalysis]:
    with get_session(engine) as session:
        return session.exec(
            select(models.WebsiteAnalysis)
            .where(models.WebsiteAnalysis.lead_id == lead_id)
            .order_by(models.WebsiteAnalysis.analyzed_at.desc())
        ).first()


# --------------------------------------------------------------------------- #
# Core API
# --------------------------------------------------------------------------- #
def analyze_website(
    engine,
    lead: models.Lead,
    fetcher: FetcherFn = _default_fetcher,
    analyzer: AnalyzerFn = _default_analyzer_fn,
) -> models.WebsiteAnalysis:
    """Analyze a lead's website and persist the result.

    On fetch error, the analysis row is saved with ``status=ERROR`` + a
    descriptive message so the UI can report it rather than crashing.
    """
    url = lead.website or ""
    url = lead.website or ""
    try:
        html = fetcher(url)
        result = analyzer(html, lead)
        status = models.AnalysisStatus.DONE
        error_msg = None
    except Exception as exc:
        html = ""
        result = {}
        status = models.AnalysisStatus.ERROR
        error_msg = (
            f"抓取失败（{url or '无网址'}）："
            + str(exc)[:300]
        )

    with get_session(engine) as session:
        existing = session.exec(
            select(models.WebsiteAnalysis).where(
                models.WebsiteAnalysis.lead_id == lead.id
            )
        ).first()
        if existing is None:
            analysis = models.WebsiteAnalysis(lead_id=lead.id)
            session.add(analysis)
        else:
            analysis = existing

        analysis.url = url
        analysis.status = status
        analysis.summary = result.get("summary")
        analysis.technologies = json.dumps(
            result.get("technologies", []), ensure_ascii=False
        )
        analysis.analysis_score_signal = float(result.get("signal", 0.0))
        analysis.error = error_msg
        session.commit()
        session.refresh(analysis)
    return analysis


def run_analysis_for_lead(
    engine,
    lead: models.Lead,
    fetcher: FetcherFn = _default_fetcher,
    analyzer: AnalyzerFn = _default_analyzer_fn,
) -> models.WebsiteAnalysis:
    """Analyze a lead AND recompute/persist its CRM score in one step.

    ``fetcher`` / ``analyzer`` are forwarded to ``analyze_website`` so tests
    can inject stubs without touching the defaults.
    """
    analysis = analyze_website(engine, lead, fetcher=fetcher, analyzer=analyzer)
    refreshed = crm.get_lead(engine, lead.id)
    if refreshed is None:
        return analysis
    score = scoring.compute_score(refreshed, analysis)
    crm.update_lead_score(engine, lead.id, score.total)
    return analysis
