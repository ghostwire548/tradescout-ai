"""TradeScout AI - Streamlit workbench.

Builds on M0: seeds a demo campaign + 5 mock leads (no API key), lets you
edit each lead's CRM status, analyze the lead's website (offline framework
stub) and recompute its score, generate outreach messages, and manage
multiple campaigns — then export everything to Excel.
"""
from __future__ import annotations

import os
import sys

import streamlit as st

# Make the project root importable when launched via `streamlit run app.py`.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.tradescout import analysis, crm, importer, messaging, mock_data, models, scoring  # noqa: E402
from src.tradescout.config import settings  # noqa: E402
from src.tradescout.db import get_engine, init_db  # noqa: E402
from src.tradescout.export import build_leads_workbook  # noqa: E402
import pandas as pd  # noqa: E402

st.set_page_config(
    page_title=settings.app_name,
    page_icon="🛰️",
    layout="wide",
)


@st.cache_resource
def bootstrap():
    """Create the engine, ensure tables exist and seed mock data once."""
    engine = get_engine()
    init_db(engine)
    seeded = mock_data.seed_mock_data(engine)
    return engine, seeded


engine, seeded = bootstrap()

st.title(f"🛰️ {settings.app_name}")
st.caption(
    f"v{settings.app_version} · DB: `{settings.database_url}`"
    + (" · LLM 已启用" if settings.llm_api_key else " · 离线模式")
)

if seeded and "seeded_shown" not in st.session_state:
    st.info("Seeded a demo campaign + 5 mock leads (no API key required).")
    st.session_state.seeded_shown = True

# --- Campaigns -------------------------------------------------------------
st.header("Campaigns")

# Session state: track active campaign and toggles for the create/edit form.
if "active_campaign_id" not in st.session_state:
    st.session_state.active_campaign_id = None
if "show_campaign_form" not in st.session_state:
    st.session_state.show_campaign_form = False

campaigns = crm.get_campaigns(engine)

if not campaigns:
    st.warning("No campaigns found. Re-run the app to seed mock data.")
    st.stop()
else:
    # Auto-select first campaign if nothing is selected yet.
    if st.session_state.active_campaign_id not in {c.id for c in campaigns}:
        st.session_state.active_campaign_id = campaigns[0].id

    ctop1, ctop2 = st.columns([4, 1])
    with ctop1:
        active_id = st.selectbox(
            "活跃 Campaign",
            options=[c.id for c in campaigns],
            format_func=lambda cid: next(
                f"{c.name}（{c.description or ''}）" for c in campaigns if c.id == cid
            ),
            index=[c.id for c in campaigns].index(st.session_state.active_campaign_id),
            key="campaign_selector",
            label_visibility="collapsed",
        )
        st.session_state.active_campaign_id = active_id
    with ctop2:
        if st.button("➕ 新建 Campaign", use_container_width=True):
            st.session_state.show_campaign_form = True

    if st.session_state.show_campaign_form:
        with st.form("new_campaign_form"):
            new_name = st.text_input("名称", placeholder="e.g. 2026 德国展客户")
            new_desc = st.text_area("描述（可选）", placeholder="展会/渠道/备注")
            f1, f2 = st.columns(2)
            if f1.form_submit_button("✅ 创建"):
                if new_name.strip():
                    new_c = crm.create_campaign(engine, new_name, new_desc)
                    st.session_state.active_campaign_id = new_c.id
                    st.session_state.show_campaign_form = False
                    st.toast(f"已创建 Campaign「{new_c.name}」")
                    st.rerun()
                else:
                    st.error("Campaign 名称不能为空")
            if f2.form_submit_button("取消"):
                st.session_state.show_campaign_form = False
                st.rerun()

    active_campaign = next(c for c in campaigns if c.id == active_id)
    leads = crm.get_leads_for_campaign(engine, active_id)
    total_leads = len(leads)
    st.caption(
        f"当前 Campaign：**{active_campaign.name}** · 线索数 **{total_leads}** 条"
    )

# --- Bulk actions ----------------------------------------------------------
st.header(f"Leads（{active_campaign.name if campaigns else '全部'}）")
bulk1, bulk2 = st.columns(2)
if bulk1.button("🔍 分析全部官网", use_container_width=True):
    for lead in leads:
        analysis.run_analysis_for_lead(engine, lead)
    st.toast("已分析全部官网并重算评分")
    st.rerun()
if bulk2.button("🔄 重新评分（用已有分析结果）", use_container_width=True):
    for lead in leads:
        existing = analysis.get_latest_analysis(engine, lead.id)
        score = scoring.compute_score(lead, existing)
        crm.update_lead_score(engine, lead.id, score.total)
    st.toast("已根据已有分析重算评分")
    st.rerun()
if st.button("✨ 为全部线索生成话术（email）", use_container_width=True):
    n = 0
    for lead in leads:
        gen = messaging.generate_message(
            lead, analysis.get_latest_analysis(engine, lead.id), channel="email"
        )
        crm.create_message(engine, lead.id, gen.channel, gen.content)
        n += 1
    st.toast(f"已为 {n} 条线索生成并保存话术")
    st.rerun()

if not leads:
    st.info("当前 Campaign 下暂无线索。可导入 CSV 或将 Campaign 包含的数据导入。")
else:
    status_options = [s.value for s in models.CRMStatus]
    for lead in leads:
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([2.2, 1.4, 1.2, 1.6, 1])
            c1.markdown(f"**{lead.company_name}**")
            c1.caption(f"{lead.industry or '—'} · {lead.country or '—'}")
            c2.markdown(f"🌐 {lead.website or '—'}")
            c3.markdown(f"**Score:** {lead.score:.1f}")
            c3.caption(lead.contact_email or "")
            current_idx = (
                status_options.index(lead.crm_status.value)
                if lead.crm_status.value in status_options
                else 0
            )
            new_status = c4.selectbox(
                "CRM Status",
                options=status_options,
                index=current_idx,
                key=f"status_{lead.id}",
                label_visibility="collapsed",
            )
            if c5.button("Save", key=f"save_{lead.id}", use_container_width=True):
                crm.update_lead_status(engine, lead.id, models.CRMStatus(new_status))
                st.toast(f"Lead '{lead.company_name}' → {new_status}")
                st.rerun()

            # Website analysis
            existing = analysis.get_latest_analysis(engine, lead.id)
            if existing and existing.status == models.AnalysisStatus.DONE:
                techs = ", ".join(existing.technologies_list) or "—"
                st.caption(
                    f"🧠 {existing.summary} · 技术栈: {techs} · 信号 {existing.analysis_score_signal:.0f}"
                )
            if st.button(
                "🔍 分析官网",
                key=f"analyze_{lead.id}",
                use_container_width=True,
            ):
                analysis.run_analysis_for_lead(engine, lead)
                st.toast(f"已分析 '{lead.company_name}' 并重算评分")
                st.rerun()

            # --- Outreach message generation (Milestone: Message generation) ---
            with st.expander("💬 开发话术", expanded=False):
                chan = st.selectbox(
                    "渠道",
                    messaging.SUPPORTED_CHANNELS,
                    key=f"msg_chan_{lead.id}",
                    label_visibility="collapsed",
                )
                if st.button(
                    "✨ 生成话术",
                    key=f"gen_msg_{lead.id}",
                    use_container_width=True,
                ):
                    gen = messaging.generate_message(
                        lead,
                        analysis.get_latest_analysis(engine, lead.id),
                        channel=chan,
                    )
                    st.session_state[f"gen_{lead.id}"] = gen
                gen = st.session_state.get(f"gen_{lead.id}")
                if gen is not None:
                    edited = st.text_area(
                        "话术内容（可编辑后保存）",
                        value=gen.content,
                        height=200,
                        key=f"msg_edit_{lead.id}",
                    )
                    if st.button(
                        "💾 保存话术",
                        key=f"save_msg_{lead.id}",
                        use_container_width=True,
                    ):
                        crm.create_message(engine, lead.id, gen.channel, edited)
                        st.toast(f"已保存话术 → {lead.company_name}")
                        st.rerun()
                saved = crm.get_messages(engine, lead.id)
                if saved:
                    st.caption(f"已保存 {len(saved)} 条话术")
                    for m in saved[-3:]:
                        st.markdown(f"- `{m.channel}` · {m.content[:60]}…")

# --- Export ----------------------------------------------------------------
st.header("Export")
buf = build_leads_workbook(engine)
st.download_button(
    label="⬇️ Export Leads to Excel (.xlsx)",
    data=buf.getvalue(),
    file_name="tradescout_leads.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# --- CSV import (Milestone: CSV Lead import) -------------------------------
st.divider()
st.header("📥 导入 CSV")
st.caption(
    "上传 CSV → 映射字段 → 预览（新增 / 重复 / 无效）→ 确认写入当前 Campaign。"
    "本区块不支持：Google Places、官网爬取、AI 评分。"
)

# Pick target campaign for import (defaults to the currently active one).
target_campaign_id = st.selectbox(
    "导入到 Campaign",
    options=[c.id for c in campaigns],
    format_func=lambda cid: next(c.name for c in campaigns if c.id == cid),
    index=[c.id for c in campaigns].index(
        st.session_state.active_campaign_id
    ) if st.session_state.active_campaign_id in {c.id for c in campaigns} else 0,
    key="import_campaign",
) if campaigns else None

uploaded = st.file_uploader("上传 CSV 文件", type=["csv"], key="csv_upload")
if uploaded is not None:
    raw = uploaded.getvalue()
    # Only re-parse when the uploaded file actually changes.
    if st.session_state.get("csv_raw") != raw:
        st.session_state.csv_raw = raw
        st.session_state.csv_headers = importer.read_csv_headers(raw)
        st.session_state.csv_mapping = importer.suggest_mapping(
            st.session_state.csv_headers
        )
        st.session_state.csv_preview = None

    headers = st.session_state.get("csv_headers", [])
    if headers:
        st.markdown("**字段映射**（将 CSV 列映射到 Lead 字段，标 * 为必填）")
        mapping = st.session_state.csv_mapping
        cols = st.columns(len(importer.TARGET_FIELDS))
        for i, target in enumerate(importer.TARGET_FIELDS):
            options = ["— 不映射 —"] + headers
            current = mapping.get(target)
            idx = options.index(current) if current in options else 0
            chosen = cols[i].selectbox(
                importer.TARGET_LABELS[target],
                options=options,
                index=idx,
                key=f"map_{target}",
            )
            mapping[target] = None if chosen == "— 不映射 —" else chosen
        st.session_state.csv_mapping = mapping

        if st.button("👁 预览导入", key="csv_preview_btn", width="stretch"):
            st.session_state.csv_preview = importer.analyze_csv(
                engine, raw, mapping
            )

        preview = st.session_state.get("csv_preview")
        if preview is not None:
            m1, m2, m3 = st.columns(3)
            m1.metric("新增", preview.new_count)
            m2.metric("重复", preview.duplicate_count)
            m3.metric("无效", preview.invalid_count)

            table = [
                {
                    "行": r.candidate.row_index + 1,
                    "公司": r.candidate.company_name or "—",
                    "网站": r.candidate.website or "—",
                    "电话": r.candidate.phone or "—",
                    "邮箱": r.candidate.email or "—",
                    "状态": r.status,
                    "原因": r.reason,
                }
                for r in preview.rows
            ]
            st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)

            if preview.new_count > 0:
                if st.button("✅ 确认导入", key="csv_confirm_btn",
                             type="primary", width="stretch"):
                    n = importer.commit_import(
                        engine, preview.new_candidates, campaign_id=target_campaign_id
                    )
                    st.toast(f"已导入 {n} 条新线索")
                    st.session_state.csv_preview = None
                    st.rerun()
            else:
                st.info("没有可导入的新线索（全部重复或无效）。")
