"""PDF investigation report (plan §10.3) using ReportLab.

FIX: every table cell is wrapped in a Paragraph flowable so long content
(metadata, hashes, source references) wraps inside its column instead of
overflowing the page. Metadata is rendered as readable key=value pairs.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select

from app.config.settings import get_settings
from app.db.models import (Alert, Case, CaseNote, Event, EvidenceItem,
                           Explanation, FeatureWindow)
from app.ingestion.hashing import sha256_file
from app.util.ids import utcnow

_styles = getSampleStyleSheet()
H1 = ParagraphStyle("h1x", parent=_styles["Heading1"], fontSize=16)
H2 = ParagraphStyle("h2x", parent=_styles["Heading2"], fontSize=12, spaceBefore=10)
BODY = _styles["BodyText"]
CELL = ParagraphStyle("cell", parent=_styles["BodyText"], fontSize=7, leading=9)
CELL_BOLD = ParagraphStyle("cellb", parent=CELL, fontName="Helvetica-Bold")
NOTE = ParagraphStyle("notex", parent=_styles["BodyText"], fontSize=8)

CHRONO_MAX_ROWS = 120


def _fmt_ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC") if dt else "-"


def _esc(text) -> str:
    """Escape XML-special characters for Paragraph safety."""
    s = "" if text is None else str(text)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _cell(text, bold: bool = False):
    return Paragraph(_esc(text), CELL_BOLD if bold else CELL)


def _fmt_detail(metadata: dict, limit: int = 100) -> str:
    """Human-readable, wrappable metadata summary (key=value, comma separated)."""
    if not metadata:
        return "-"
    s = ", ".join(f"{k}={v}" for k, v in metadata.items())
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    return s


def _table(rows, widths, header: bool = True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    style = [
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dde7f0")))
    t.setStyle(TableStyle(style))
    return t


def _kv_table(pairs, widths=(45 * mm, 135 * mm)):
    rows = [[_cell(k, bold=True), _cell(v)] for k, v in pairs]
    return _table(rows, list(widths), header=False)


def build_case_pdf(db, case: Case) -> tuple[Path, str]:
    out_dir = get_settings().cases_dir / case.id
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / "report.pdf"

    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4,
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm,
                            title=f"XAI-Insider Case {case.id}")
    story = []

    story.append(Paragraph("XAI-Insider - Investigation Report", H1))
    story.append(Paragraph("<b>SYNTHETIC LAB DEMONSTRATION - NOT REAL EVIDENCE</b>", BODY))
    story.append(Spacer(1, 6))

    story.append(_kv_table([
        ("Case ID", case.id), ("Title", case.title),
        ("Status", case.status), ("Disposition", case.disposition or "-"),
        ("Priority", case.priority), ("Generated (UTC)", _fmt_ts(utcnow())),
        ("Created (UTC)", _fmt_ts(case.created_at)),
    ]))

    # ---------------- Detection results ----------------
    story.append(Paragraph("Detection results", H2))
    alerts = [a for a in (db.get(Alert, aid) for aid in case.alert_ids) if a]
    if not alerts:
        story.append(Paragraph("No alerts linked.", NOTE))

    for a in alerts:
        story.append(_kv_table([
            ("Alert ID", a.id), ("Employee (pseudonym)", a.employee_id),
            ("Window", f"{_fmt_ts(a.window_start)} - {_fmt_ts(a.window_end)}"),
            ("Normalized score", f"{a.normalized_score:.1f}"),
            ("Priority score / band", f"{a.priority_score:.1f} / {a.priority_band.upper()}"),
            ("Analysis run", a.run_id),
        ]))
        story.append(Spacer(1, 4))

        expl = db.execute(select(Explanation)
                          .where(Explanation.alert_id == a.id)).scalars().first()
        if expl:
            story.append(Paragraph(
                f"Explanation (method: {_esc(expl.method)}; baseline: {_esc(expl.baseline_used)})",
                NOTE))
            erows = [[_cell("Feature", True), _cell("Observed", True),
                      _cell("Baseline median", True), _cell("Robust z", True),
                      _cell("Ablation delta", True)]]
            for r in expl.feature_reasons:
                erows.append([_cell(r["feature"]), _cell(f"{r['observed']:.4g}"),
                              _cell(f"{r['baseline_median']:.4g}"),
                              _cell(f"{r['robust_z']:+.2f}"),
                              _cell(f"{r['ablation_delta_score']:+.4f}")])
            story.append(_table(erows, [52 * mm, 28 * mm, 32 * mm, 24 * mm, 30 * mm]))
            story.append(Paragraph(f"Caveat: {_esc(expl.caveats)}", NOTE))
            story.append(Spacer(1, 4))

    # ---------------- Chronology (wrapped cells, fits page) ----------------
    story.append(Paragraph("Chronology (linked alert windows)", H2))
    event_rows = [[_cell("Time (UTC)", True), _cell("Employee", True),
                   _cell("Host", True), _cell("Type", True), _cell("Detail", True)]]
    seen, flat = set(), []
    for a in alerts:
        window = db.get(FeatureWindow, a.window_id)
        if not window:
            continue
        evs = db.execute(select(Event)
                         .where(Event.id.in_(window.source_event_ids))).scalars().all()
        flat.extend(e for e in evs if e.id not in seen and not seen.add(e.id))
    flat.sort(key=lambda e: e.timestamp_utc)

    for e in flat[:CHRONO_MAX_ROWS]:
        event_rows.append([_cell(_fmt_ts(e.timestamp_utc)), _cell(e.employee_id),
                           _cell(e.host_id), _cell(e.event_type),
                           _cell(_fmt_detail(e.metadata_))])
    if len(flat) > 1:
        story.append(_table(event_rows, [34 * mm, 22 * mm, 20 * mm, 24 * mm, 80 * mm]))
        if len(flat) > CHRONO_MAX_ROWS:
            story.append(Paragraph(
                f"Showing first {CHRONO_MAX_ROWS} of {len(flat)} events; "
                f"the full list is included in the evidence ZIP.", NOTE))
    else:
        story.append(Paragraph("No events collected.", NOTE))

    # ---------------- Evidence register ----------------
    story.append(Paragraph("Evidence register", H2))
    items = db.execute(select(EvidenceItem)
                       .where(EvidenceItem.case_id == case.id)).scalars().all()
    if items:
        rows = [[_cell(h, True) for h in ("Item", "Type", "Source reference",
                                          "SHA-256", "Integrity")]]
        for it in items:
            rows.append([_cell(it.id), _cell(it.item_type),
                         _cell(it.source_reference), _cell(it.sha256),
                         _cell(it.integrity_status)])
        story.append(_table(rows, [32 * mm, 22 * mm, 48 * mm, 56 * mm, 20 * mm]))
    else:
        story.append(Paragraph("No evidence items collected.", NOTE))

    # ---------------- Notes & disposition ----------------
    story.append(Paragraph("Investigator notes", H2))
    notes = db.execute(select(CaseNote).where(CaseNote.case_id == case.id)
                       .order_by(CaseNote.created_at)).scalars().all()
    for n in notes:
        story.append(Paragraph(f"[{_fmt_ts(n.created_at)}] {_esc(n.note_text)}", NOTE))
    if case.disposition_rationale:
        story.append(Paragraph(f"Disposition rationale: {_esc(case.disposition_rationale)}", NOTE))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "This report was generated from synthetic lab data. An anomaly score is not proof of "
        "misconduct. All timestamps and identities are simulated.", NOTE))

    doc.build(story)
    return pdf_path, sha256_file(pdf_path)