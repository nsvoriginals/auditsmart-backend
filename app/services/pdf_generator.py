"""
AuditSmart v2.0 — PDF Audit Report Generator

Generates professional, branded PDF audit reports that users can download.
Available in FREE tier too (as per Rajat's requirement).
Uses reportlab for PDF generation — no external services needed.
"""

import io
import base64
from datetime import datetime
from typing import Dict, List, Optional

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm, inch
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable, Image
    )
    from reportlab.graphics.shapes import Drawing, Rect, Circle, String
    from reportlab.graphics.charts.piecharts import Pie
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("⚠️ reportlab not installed — PDF generation disabled")
    print("   Install with: pip install reportlab")


# AuditSmart brand colors
COLORS = {
    "bg_dark": HexColor("#060612") if REPORTLAB_AVAILABLE else None,
    "cyan": HexColor("#00e8ff") if REPORTLAB_AVAILABLE else None,
    "cyan_dark": HexColor("#0099cc") if REPORTLAB_AVAILABLE else None,
    "magenta": HexColor("#c840ff") if REPORTLAB_AVAILABLE else None,
    "green": HexColor("#00ff88") if REPORTLAB_AVAILABLE else None,
    "red": HexColor("#ff3366") if REPORTLAB_AVAILABLE else None,
    "orange": HexColor("#ff6b00") if REPORTLAB_AVAILABLE else None,
    "yellow": HexColor("#ffbe0b") if REPORTLAB_AVAILABLE else None,
    "text": HexColor("#222222") if REPORTLAB_AVAILABLE else None,
    "text_light": HexColor("#666666") if REPORTLAB_AVAILABLE else None,
    "bg_light": HexColor("#f8f9fa") if REPORTLAB_AVAILABLE else None,
    "border": HexColor("#dee2e6") if REPORTLAB_AVAILABLE else None,
    "critical_bg": HexColor("#fff0f3") if REPORTLAB_AVAILABLE else None,
    "high_bg": HexColor("#fff3e0") if REPORTLAB_AVAILABLE else None,
    "medium_bg": HexColor("#fffde7") if REPORTLAB_AVAILABLE else None,
    "low_bg": HexColor("#e8f5e9") if REPORTLAB_AVAILABLE else None,
}

SEVERITY_COLORS = {
    "critical": HexColor("#ff3366") if REPORTLAB_AVAILABLE else None,
    "high": HexColor("#ff6b00") if REPORTLAB_AVAILABLE else None,
    "medium": HexColor("#ffbe0b") if REPORTLAB_AVAILABLE else None,
    "low": HexColor("#00ff88") if REPORTLAB_AVAILABLE else None,
    "info": HexColor("#0099cc") if REPORTLAB_AVAILABLE else None,
}

SEVERITY_BG = {
    "critical": HexColor("#fff0f3") if REPORTLAB_AVAILABLE else None,
    "high": HexColor("#fff8f0") if REPORTLAB_AVAILABLE else None,
    "medium": HexColor("#fffdf0") if REPORTLAB_AVAILABLE else None,
    "low": HexColor("#f0fff4") if REPORTLAB_AVAILABLE else None,
    "info": HexColor("#f0f8ff") if REPORTLAB_AVAILABLE else None,
}


def _get_styles():
    """Create custom paragraph styles for the report."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        'ReportTitle',
        parent=styles['Title'],
        fontSize=24,
        textColor=HexColor("#060612"),
        spaceAfter=6,
        fontName='Helvetica-Bold'
    ))

    styles.add(ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=HexColor("#666666"),
        spaceAfter=20,
    ))

    styles.add(ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=HexColor("#060612"),
        spaceBefore=20,
        spaceAfter=10,
        fontName='Helvetica-Bold',
        borderWidth=0,
        borderPadding=0,
    ))

    styles.add(ParagraphStyle(
        'FindingTitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=HexColor("#222222"),
        fontName='Helvetica-Bold',
        spaceBefore=8,
        spaceAfter=4,
    ))

    styles.add(ParagraphStyle(
        'FindingBody',
        parent=styles['Normal'],
        fontSize=10,
        textColor=HexColor("#333333"),
        spaceAfter=4,
        leading=14,
    ))

    styles.add(ParagraphStyle(
        'Recommendation',
        parent=styles['Normal'],
        fontSize=10,
        textColor=HexColor("#1a7f37"),
        leftIndent=12,
        spaceAfter=8,
        leading=14,
        fontName='Helvetica-Oblique',
    ))

    styles.add(ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=HexColor("#999999"),
        alignment=TA_CENTER,
    ))

    return styles


def generate_audit_pdf(audit_data: Dict) -> Optional[bytes]:
    """
    Generate a professional PDF audit report.
    
    Returns PDF as bytes, or None if reportlab is not available.
    """
    if not REPORTLAB_AVAILABLE:
        return None

    buffer = io.BytesIO()
    styles = _get_styles()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=25 * mm,
        leftMargin=25 * mm,
        topMargin=25 * mm,
        bottomMargin=25 * mm,
        title=f"AuditSmart Security Report — {audit_data.get('contract_name', 'Contract')}",
        author="AuditSmart AI Security Platform"
    )

    elements = []

    # ═══ HEADER / TITLE ═══
    elements.append(Paragraph(
        "AUDITSMART",
        ParagraphStyle('Brand', parent=styles['Normal'],
                       fontSize=10, textColor=HexColor("#0099cc"),
                       fontName='Helvetica-Bold',
                       spaceAfter=2, letterSpacing=4)
    ))
    elements.append(Paragraph(
        "AI SECURITY PLATFORM",
        ParagraphStyle('BrandSub', parent=styles['Normal'],
                       fontSize=7, textColor=HexColor("#999999"),
                       spaceAfter=16, letterSpacing=2)
    ))

    elements.append(HRFlowable(
        width="100%", thickness=2, color=HexColor("#0099cc"),
        spaceAfter=16
    ))

    elements.append(Paragraph(
        f"Security Audit Report",
        styles['ReportTitle']
    ))

    contract_name = audit_data.get("contract_name", "Contract")
    chain = audit_data.get("chain", "ethereum")
    created = audit_data.get("created_at", "")
    if isinstance(created, datetime):
        created = created.strftime("%B %d, %Y at %H:%M UTC")
    elif isinstance(created, str) and created:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            created = dt.strftime("%B %d, %Y at %H:%M UTC")
        except Exception:
            pass

    elements.append(Paragraph(
        f"Contract: <b>{contract_name}</b> &nbsp;|&nbsp; "
        f"Chain: <b>{chain.capitalize()}</b> &nbsp;|&nbsp; "
        f"Date: <b>{created or 'N/A'}</b>",
        styles['ReportSubtitle']
    ))

    # ═══ EXECUTIVE SUMMARY ═══
    elements.append(Paragraph("Executive Summary", styles['SectionHeader']))

    risk_score = audit_data.get("risk_score", 0)
    risk_level = audit_data.get("risk_level", "unknown").upper()
    total = audit_data.get("total_findings", 0)
    critical = audit_data.get("critical_count", 0)
    high = audit_data.get("high_count", 0)
    medium = audit_data.get("medium_count", 0)
    low = audit_data.get("low_count", 0)
    agents_used = audit_data.get("agents_used", [])
    duration = audit_data.get("scan_duration_ms", 0)

    # Summary table
    summary_data = [
        ["Risk Score", f"{risk_score}/100 ({risk_level})"],
        ["Total Findings", str(total)],
        ["Critical", str(critical)],
        ["High", str(high)],
        ["Medium", str(medium)],
        ["Low", str(low)],
        ["Agents Used", str(len(agents_used))],
        ["Scan Duration", f"{duration}ms"],
    ]

    summary_table = Table(summary_data, colWidths=[130, 350])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), HexColor("#f0f8ff")),
        ('TEXTCOLOR', (0, 0), (0, -1), HexColor("#333333")),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor("#dee2e6")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        # Color the risk score row based on severity
        ('TEXTCOLOR', (1, 0), (1, 0),
         SEVERITY_COLORS.get(risk_level.lower(), HexColor("#333333"))),
        ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 16))

    # Summary paragraph
    summary_text = audit_data.get("summary", "")
    if summary_text:
        elements.append(Paragraph(summary_text, styles['FindingBody']))
        elements.append(Spacer(1, 12))

    # ═══ FINDINGS ═══
    elements.append(Paragraph("Detailed Findings", styles['SectionHeader']))
    elements.append(HRFlowable(
        width="100%", thickness=1, color=HexColor("#dee2e6"),
        spaceAfter=12
    ))

    findings = audit_data.get("findings", [])
    if not findings:
        elements.append(Paragraph(
            "No vulnerabilities detected.",
            styles['FindingBody']
        ))
    else:
        for i, finding in enumerate(findings, 1):
            sev = finding.get("severity", "info").lower()
            sev_color = SEVERITY_COLORS.get(sev, HexColor("#666666"))
            sev_bg = SEVERITY_BG.get(sev, HexColor("#f8f9fa"))

            # Finding header with severity badge
            finding_type = finding.get("type", "Unknown")
            line = finding.get("line", "")
            func = finding.get("function", "")
            confidence = finding.get("confidence", "")

            header_text = (
                f'<font color="{sev_color.hexval()}">[{sev.upper()}]</font> '
                f'#{i} — {finding_type}'
            )
            if line:
                header_text += f' <font color="#999999">(Line {line})</font>'
            if func:
                header_text += f' <font color="#999999">in {func}()</font>'

            elements.append(Paragraph(header_text, styles['FindingTitle']))

            # Description
            desc = finding.get("description", "No description provided.")
            elements.append(Paragraph(desc, styles['FindingBody']))

            # Confidence indicator
            if confidence:
                conf_text = f'Confidence: {confidence.upper()}'
                confirmed = finding.get("confirmed_by", [])
                if confirmed:
                    conf_text += f' — detected by {len(confirmed)} agents'
                elements.append(Paragraph(
                    f'<font color="#0099cc">{conf_text}</font>',
                    ParagraphStyle('Conf', parent=styles['Normal'],
                                   fontSize=9, spaceAfter=4)
                ))

            # Recommendation
            rec = finding.get("recommendation", "")
            if rec:
                elements.append(Paragraph(
                    f"→ Recommendation: {rec}",
                    styles['Recommendation']
                ))

            elements.append(HRFlowable(
                width="100%", thickness=0.5, color=HexColor("#eee"),
                spaceAfter=8, spaceBefore=4
            ))

    # ═══ FOOTER / DISCLAIMER ═══
    elements.append(Spacer(1, 30))
    elements.append(HRFlowable(
        width="100%", thickness=1, color=HexColor("#0099cc"),
        spaceAfter=12
    ))

    elements.append(Paragraph(
        "This report was generated by AuditSmart AI Security Platform. "
        "It is a pre-audit triage tool and does not replace a full manual security audit. "
        "AuditSmart uses multi-agent AI analysis to identify potential vulnerabilities, "
        "but no automated tool can guarantee 100% coverage. "
        "For production contracts handling significant value, a professional manual audit is recommended.",
        ParagraphStyle('Disclaimer', parent=styles['Normal'],
                       fontSize=8, textColor=HexColor("#999999"),
                       spaceAfter=8, leading=11)
    ))

    elements.append(Paragraph(
        f"Generated on {datetime.utcnow().strftime('%B %d, %Y at %H:%M UTC')} "
        f"— auditsmart.org",
        styles['Footer']
    ))

    # Build PDF
    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    return pdf_bytes


def pdf_to_base64(pdf_bytes: bytes) -> str:
    """Convert PDF bytes to base64 string for API response."""
    return base64.b64encode(pdf_bytes).decode('utf-8')
