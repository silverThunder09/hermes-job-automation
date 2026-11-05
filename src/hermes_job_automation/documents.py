import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from xml.sax.saxutils import escape

from .models import Posting


def _slug(value: str) -> str:
    result = re.sub(r"[^\w가-힣.-]+", "_", value, flags=re.UNICODE).strip("_.")
    return result[:60] or "company"


def _korean_font_name() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    configured_font = os.environ.get("JOB_ASSIST_PDF_FONT", "").strip()
    candidates = ([Path(configured_font).expanduser()] if configured_font else []) + [
        windows_dir / "Fonts" / "malgun.ttf",
        windows_dir / "Fonts" / "malgunbd.ttf",
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf"),
    ]
    if configured_font and not candidates[0].is_file():
        raise RuntimeError("JOB_ASSIST_PDF_FONT must point to an existing Korean TrueType font.")
    font_path = next((path for path in candidates if path.is_file()), None)
    if font_path is None:
        raise RuntimeError(
            "A Korean TrueType font is required: install Malgun Gothic on Windows "
            "or fonts-nanum on Linux, or set JOB_ASSIST_PDF_FONT to a .ttf file."
        )
    font_name = "JobAssistKorean_" + font_path.stem
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
    return font_name


def _write_pdf(path: Path, posting: Posting, label: str, text: str) -> None:
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    font_name = _korean_font_name()
    title_style = ParagraphStyle(
        "JobAssistTitle", fontName=font_name, fontSize=16, leading=22, spaceAfter=12
    )
    body_style = ParagraphStyle(
        "JobAssistBody", fontName=font_name, fontSize=10, leading=16,
        alignment=TA_LEFT, spaceAfter=8
    )
    meta_style = ParagraphStyle(
        "JobAssistMeta", fontName=font_name, fontSize=9, leading=13, spaceAfter=5
    )
    story = [
        Paragraph(escape("{} 지원용 {}".format(posting.company, label)), title_style),
        Paragraph(escape(posting.title), meta_style),
        Paragraph(escape(posting.url), meta_style),
        Paragraph("작성본은 제출 전에 원문 이력서와 대조해 검토하세요.", meta_style),
        Spacer(1, 8),
    ]
    for block in text.split("\n\n"):
        if block.strip():
            story.append(Paragraph(escape(block.strip()).replace("\n", "<br/>"), body_style))
    SimpleDocTemplate(
        str(path), pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="{} 지원용 {}".format(posting.company, label),
    ).build(story)


def create_application_documents(
    output_dir: Path,
    posting: Posting,
    resume_text: str,
    cover_letter_text: str,
) -> List[Path]:
    if not resume_text.strip() or not cover_letter_text.strip():
        raise ValueError("Resume and cover letter text must both be reviewed before saving.")
    try:
        from docx import Document
        from docx.shared import Pt
    except ImportError as exc:
        raise RuntimeError("Install python-docx to generate application documents.") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    company_dir = output_dir / _slug(posting.company)
    company_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    files = []
    for label, text in (("이력서", resume_text), ("자기소개서", cover_letter_text)):
        document = Document()
        normal = document.styles["Normal"]
        normal.font.name = "Malgun Gothic"
        normal.font.size = Pt(10)
        document.add_heading("{} 지원용 {}".format(posting.company, label), level=1)
        document.add_paragraph(posting.title)
        document.add_paragraph(posting.url)
        document.add_paragraph("작성본은 제출 전에 원문 이력서와 대조해 검토하세요.")
        for block in text.split("\n\n"):
            if block.strip():
                document.add_paragraph(block.strip())
        stem = "{}_{}_{}".format(_slug(posting.company), label, stamp)
        docx_path = company_dir / (stem + ".docx")
        document.save(str(docx_path))
        files.append(docx_path)
        pdf_path = company_dir / (stem + ".pdf")
        _write_pdf(pdf_path, posting, label, text)
        files.append(pdf_path)
    return files