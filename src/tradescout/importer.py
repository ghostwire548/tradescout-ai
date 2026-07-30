"""CSV Lead import: parsing, field mapping, normalization, dedup, persistence.

Milestone scope (CSV Lead import only):
- Upload a CSV, map source columns to Lead fields, normalize values, dedupe
  (prefer website domain, else company name + phone), preview the result, then
  commit only the *new* rows inside a single transaction.

Deliberately NOT implemented here (separate milestones):
- Google Places / website crawling
- AI scoring or outreach message generation
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import crm, models

# Target Lead fields the user is allowed to map from the CSV.
TARGET_FIELDS = [
    "company_name",
    "website",
    "phone",
    "email",
    "address",
    "country",
    "city",
    "category",
]

# Human-facing labels (Chinese) for the mapping UI.
TARGET_LABELS = {
    "company_name": "公司名称 *",
    "website": "网站",
    "phone": "电话",
    "email": "邮箱",
    "address": "地址",
    "country": "国家",
    "city": "城市",
    "category": "类别 / 行业",
}

# Aliases used to auto-suggest a mapping from CSV headers (case-insensitive).
TARGET_ALIASES = {
    "company_name": ["company", "company name", "company_name", "name", "business",
                     "客户", "公司", "公司名称"],
    "website": ["website", "web", "url", "site", "主页", "网址", "网站"],
    "phone": ["phone", "tel", "telephone", "mobile", "电话", "手机", "联系电话"],
    "email": ["email", "e-mail", "mail", "邮箱", "电子邮件", "邮件"],
    "address": ["address", "addr", "地址", "详细地址"],
    "country": ["country", "国家", "国家/地区"],
    "city": ["city", "城市", "town"],
    "category": ["category", "industry", "sector", "行业", "类别", "分类"],
}


# --------------------------------------------------------------------------- #
# Normalization helpers (pure functions, easy to unit-test)
# --------------------------------------------------------------------------- #
def normalize_company_name(raw: Optional[str]) -> str:
    """Strip and collapse whitespace. Returns '' when empty."""
    if raw is None:
        return ""
    s = str(raw).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_domain(raw: Optional[str]) -> Optional[str]:
    """Extract a canonical host (no scheme/www/path) lower-cased. None if empty."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", s)  # drop scheme
    s = re.sub(r"^www\.", "", s)                  # drop leading www.
    s = s.split("/")[0].split("?")[0].split("#")[0]
    s = s.strip().strip("@").rstrip(".")
    return s or None


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Keep digits (and a leading '+'); drop spaces, dashes, parens, dots."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    has_plus = s.startswith("+")
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None
    return ("+" + digits) if has_plus else digits


def normalize_email(raw: Optional[str]) -> Optional[str]:
    """Lower-case and strip. None when empty."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    return s or None


def normalize_text(raw: Optional[str]) -> Optional[str]:
    """Strip and collapse whitespace for free-text fields. None when empty."""
    if raw is None:
        return None
    s = str(raw).strip()
    s = re.sub(r"\s+", " ", s)
    return s or None


# --------------------------------------------------------------------------- #
# Data containers
# --------------------------------------------------------------------------- #
@dataclass
class Candidate:
    row_index: int
    company_name: str
    website: Optional[str] = None
    domain: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    category: Optional[str] = None
    raw: Dict[str, str] = field(default_factory=dict)


@dataclass
class ClassifiedRow:
    candidate: Candidate
    status: str          # "new" | "duplicate" | "invalid"
    reason: str


@dataclass
class ImportPreview:
    rows: List[ClassifiedRow]
    new_count: int
    duplicate_count: int
    invalid_count: int
    new_candidates: List[Candidate] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# CSV reading + mapping
# --------------------------------------------------------------------------- #
def _decode(raw_bytes: bytes) -> str:
    """Decode CSV bytes, trying common encodings (incl. GBK for Chinese files)."""
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("latin-1")


def read_csv(raw_bytes: bytes) -> List[Dict[str, str]]:
    """Parse CSV bytes into a list of row dicts (keys = header names)."""
    text = _decode(raw_bytes)
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def read_csv_headers(raw_bytes: bytes) -> List[str]:
    """Return the CSV header names without loading the whole file."""
    text = _decode(raw_bytes)
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        return [h.strip() for h in row]
    return []


def suggest_mapping(headers: List[str]) -> Dict[str, Optional[str]]:
    """Auto-map target fields to CSV headers using alias matching."""
    mapping: Dict[str, Optional[str]] = {t: None for t in TARGET_FIELDS}
    used: set[str] = set()
    norm_headers = [(h.strip().lower(), h) for h in headers]
    for target, aliases in TARGET_ALIASES.items():
        for hnorm, horig in norm_headers:
            if hnorm in used:
                continue
            if hnorm in aliases or any(a in hnorm for a in aliases):
                mapping[target] = horig
                used.add(hnorm)
                break
    return mapping


def build_candidates(rows: List[Dict[str, str]],
                     mapping: Dict[str, Optional[str]]) -> List[Candidate]:
    """Map + normalize each CSV row into a Candidate (no dedup yet)."""
    candidates: List[Candidate] = []
    for i, row in enumerate(rows):
        def get(target: str) -> Optional[str]:
            src = mapping.get(target)
            if not src:
                return None
            val = row.get(src)
            return val if isinstance(val, str) else (str(val) if val is not None else None)

        website_raw = get("website")
        domain = normalize_domain(website_raw)
        candidates.append(
            Candidate(
                row_index=i,
                company_name=normalize_company_name(get("company_name")),
                website=domain,
                domain=domain,
                phone=normalize_phone(get("phone")),
                email=normalize_email(get("email")),
                address=normalize_text(get("address")),
                country=normalize_text(get("country")),
                city=normalize_text(get("city")),
                category=normalize_text(get("category")),
                raw=row,
            )
        )
    return candidates


# --------------------------------------------------------------------------- #
# Dedup
# --------------------------------------------------------------------------- #
def _lead_dedup_key(lead: models.Lead):
    """Compute the dedup key for an existing Lead row."""
    domain = normalize_domain(lead.website)
    if domain:
        return ("domain", domain)
    name = normalize_company_name(lead.company_name)
    phone = normalize_phone(lead.phone) or ""
    if name:
        return ("name_phone", name, phone)
    return None


def dedup_key(candidate: Candidate):
    """Compute the dedup key for a Candidate."""
    if candidate.domain:
        return ("domain", candidate.domain)
    return ("name_phone", candidate.company_name, candidate.phone or "")


def _existing_keys(engine) -> set:
    keys: set = set()
    for lead in crm.get_leads(engine):
        key = _lead_dedup_key(lead)
        if key:
            keys.add(key)
    return keys


# --------------------------------------------------------------------------- #
# Preview + commit
# --------------------------------------------------------------------------- #
def preview_candidates(engine, candidates: List[Candidate]) -> ImportPreview:
    """Classify candidates into new / duplicate / invalid (no writes)."""
    existing_keys = _existing_keys(engine)
    seen_new: set = set()
    classified: List[ClassifiedRow] = []
    new_candidates: List[Candidate] = []

    for c in candidates:
        if not c.company_name:
            status, reason = "invalid", "缺少公司名称"
        else:
            key = dedup_key(c)
            if key in existing_keys or key in seen_new:
                status, reason = "duplicate", "与已有 / 批量线索重复"
            else:
                status, reason = "new", "可导入"
                seen_new.add(key)
                new_candidates.append(c)
        classified.append(ClassifiedRow(candidate=c, status=status, reason=reason))

    return ImportPreview(
        rows=classified,
        new_count=sum(1 for r in classified if r.status == "new"),
        duplicate_count=sum(1 for r in classified if r.status == "duplicate"),
        invalid_count=sum(1 for r in classified if r.status == "invalid"),
        new_candidates=new_candidates,
    )


def analyze_csv(engine, raw_bytes: bytes,
                mapping: Dict[str, Optional[str]]) -> ImportPreview:
    """Full preview pipeline: parse -> map -> classify."""
    rows = read_csv(raw_bytes)
    candidates = build_candidates(rows, mapping)
    return preview_candidates(engine, candidates)


def commit_import(engine, candidates: List[Candidate],
                 campaign_id: Optional[int] = None) -> int:
    """Persist only the given (new) candidates inside one transaction.

    On any failure the whole batch is rolled back, so pre-existing data is
    never corrupted. Returns the number of inserted leads.

    If *campaign_id* is not given, the default campaign is used (creating
    one if no campaign exists yet).
    """
    if not candidates:
        return 0
    if campaign_id is None:
        campaign_id = crm.ensure_default_campaign(engine)
    with crm.get_session(engine) as session:
        try:
            for c in candidates:
                session.add(
                    models.Lead(
                        campaign_id=campaign_id,
                        company_name=c.company_name,
                        website=c.website,
                        industry=c.category,            # category -> industry
                        country=c.country,
                        contact_email=c.email,          # email -> contact_email
                        phone=c.phone,
                        address=c.address,
                        city=c.city,
                        score=0.0,
                        crm_status=models.CRMStatus.NEW,
                    )
                )
            session.commit()
        except Exception:
            session.rollback()
            raise
    return len(candidates)
