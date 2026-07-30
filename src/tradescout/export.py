"""Export leads to Excel (.xlsx) using openpyxl."""
from __future__ import annotations

import io
from sqlmodel import select

from . import models
from .db import get_session


def build_leads_workbook(engine) -> io.BytesIO:
    """Build an .xlsx workbook of all leads and return it as a BytesIO buffer."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"

    headers = [
        "ID",
        "Company",
        "Website",
        "Industry",
        "Country",
        "Contact Email",
        "Score",
        "CRM Status",
        "Website Analysis",
        "Created At",
    ]
    ws.append(headers)

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF")
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    with get_session(engine) as session:
        leads = session.exec(select(models.Lead)).all()
        analyses = session.exec(
            select(models.WebsiteAnalysis).order_by(
                models.WebsiteAnalysis.lead_id,
                models.WebsiteAnalysis.analyzed_at.desc(),
            )
        ).all()
    # For leads analysed multiple times the latest (sorted first) wins.
    by_lead = {a.lead_id: a for a in analyses}

    for lead in leads:
        analysis = by_lead.get(lead.id)
        analysis_text = (
            analysis.summary
            if (analysis and analysis.status == models.AnalysisStatus.DONE)
            else ""
        )
        ws.append(
            [
                lead.id,
                lead.company_name,
                lead.website or "",
                lead.industry or "",
                lead.country or "",
                lead.contact_email or "",
                lead.score,
                lead.crm_status.value if lead.crm_status else "",
                analysis_text,
                lead.created_at.isoformat() if lead.created_at else "",
            ]
        )

    for col in ws.columns:
        length = max(
            (len(str(c.value)) for c in col if c.value is not None), default=10
        )
        ws.column_dimensions[col[0].column_letter].width = min(max(length + 2, 10), 60)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def export_leads_xlsx(engine, file_path: str = "leads_export.xlsx") -> str:
    """Write the leads workbook to a file and return the path."""
    buf = build_leads_workbook(engine)
    with open(file_path, "wb") as f:
        f.write(buf.getvalue())
    return file_path
