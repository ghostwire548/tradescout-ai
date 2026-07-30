"""Milestone 1 tests: website analysis framework + lead scoring."""
import os
import tempfile

from sqlmodel import select

from src.tradescout import analysis, crm, models, scoring
from src.tradescout.db import get_engine, get_session, init_db


def _make_engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # we only want the path; sqlite will create the file
    engine = get_engine(f"sqlite:///{path}")
    init_db(engine)
    return engine, path


def _cleanup(engine, path):
    engine.dispose()
    if os.path.exists(path):
        os.remove(path)


def test_website_analysis_persists():
    """Analysis persists correctly when fetching succeeds."""
    engine, path = _make_engine()
    try:
        lead = models.Lead(company_name="X", website="https://x.example.com")
        with get_session(engine) as session:
            session.add(lead)
            session.commit()
            session.refresh(lead)

        # Inject a stub fetcher that returns realistic HTML so the heuristic
        # analyzer finds a title + meta description.
        def test_fetcher(url):
            return (
                "<html><head>"
                "<title>Acme Corp - Industrial Supplies</title>"
                '<meta name="description" content="Quality since 1990">'
                "</head><body></body></html>"
            )

        result = analysis.analyze_website(engine, lead, fetcher=test_fetcher)
        assert result.status == models.AnalysisStatus.DONE
        assert result.lead_id == lead.id
        assert "Acme Corp" in (result.summary or "")
        assert "Quality since 1990" in (result.summary or "")

        again = analysis.get_latest_analysis(engine, lead.id)
        assert again is not None
        assert again.summary
    finally:
        _cleanup(engine, path)


def test_default_scorer_range_and_deterministic():
    lead = models.Lead(
        company_name="Y",
        website="https://y.example.com",
        country="Germany",
        industry="Machinery",
        contact_email="a@b.com",
    )
    r1 = scoring.default_scorer(lead)
    r2 = scoring.default_scorer(lead)
    assert 0.0 <= r1.total <= 100.0
    assert r1.total == r2.total  # deterministic
    assert "analysis_signal" in r1.factors


def test_scorer_includes_analysis_signal():
    lead = models.Lead(company_name="Z", website="https://z.example.com")
    no_analysis = scoring.compute_score(lead, None)
    done = models.WebsiteAnalysis(
        status=models.AnalysisStatus.DONE, analysis_score_signal=40.0
    )
    with_analysis = scoring.compute_score(lead, done)
    assert with_analysis.total > no_analysis.total  # analysis adds signal points


def test_country_scoring_case_insensitive():
    """Country lookup should match regardless of case (USA/usa/Usa all → 20)."""
    lead_upper = models.Lead(company_name="A", country="USA")
    lead_lower = models.Lead(company_name="A", country="usa")
    lead_mixed = models.Lead(company_name="A", country="Usa")
    s_upper = scoring.default_scorer(lead_upper)
    s_lower = scoring.default_scorer(lead_lower)
    s_mixed = scoring.default_scorer(lead_mixed)
    assert s_upper.factors["country"] == 20.0
    assert s_lower.factors["country"] == 20.0
    assert s_mixed.factors["country"] == 20.0


def test_heuristic_analyzer_title_meta_tech():
    """The default analyzer extracts title, meta desc and detects known tech."""
    html = (
        "<html><head>"
        "<title>Foo Inc</title>"
        '<meta name="description" content="Bar">'
        '<script src="jquery-3.6.0.min.js"></script>'
        '<link href="bootstrap.min.css">'
        "</head><body>" + "a" * 3000 + "</body></html>"
    )
    lead = models.Lead(company_name="Foo", website="https://foo.example.com")
    result = analysis._default_analyzer(html, lead)
    assert "Foo Inc" in result["summary"]
    assert "Bar" in result["summary"]
    assert "jQuery" in result["technologies"]
    assert "Bootstrap" in result["technologies"]
    # T(10) + M(10) + tech 2×5=10 + size>2000(5) = 35
    assert result["signal"] == 35.0


def test_heuristic_analyzer_empty_html():
    result = analysis._default_analyzer("", models.Lead(company_name="E"))
    assert result["signal"] == 0.0
    assert result["technologies"] == []


def test_fetch_error_records_error_status():
    engine, path = _make_engine()
    try:
        lead = models.Lead(company_name="Bad", website="https://no-such-domain.zzz")
        with get_session(engine) as session:
            session.add(lead)
            session.commit()
            session.refresh(lead)

        result = analysis.analyze_website(engine, lead)
        assert result.status == models.AnalysisStatus.ERROR
        assert result.error
        assert result.analysis_score_signal == 0.0
    finally:
        _cleanup(engine, path)


def test_run_analysis_updates_score():
    engine, path = _make_engine()
    try:
        lead = models.Lead(company_name="Z", website="https://z.example.com", country="USA")
        with get_session(engine) as session:
            session.add(lead)
            session.commit()
            session.refresh(lead)

        # Inject a fetcher with enough content for max heuristic signal (40).
        # Title (10) + meta desc (10) + 3 techs (15, capped) + size>2000 (5) = 40.
        def test_fetcher(url):
            return (
                "<html><head>"
                '<title>Z Corp</title>'
                '<meta name="description" content="Best in class">'
                '<script src="/jquery.min.js"></script>'
                '<link href="/bootstrap.min.css">'
                '<script async src="https://www.google-analytics.com/analytics.js"></script>'
                "</head><body>" + "x" * 3000 + "</body></html>"
            )

        analysis.run_analysis_for_lead(engine, lead, fetcher=test_fetcher)
        refreshed = crm.get_lead(engine, lead.id)
        assert refreshed.score > 0.0
        # website(20) + country USA(20) + analysis signal(40) = 80+
        assert refreshed.score >= 80.0
    finally:
        _cleanup(engine, path)
