from __future__ import annotations

from datetime import date, datetime
from email.message import EmailMessage
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Dict, Mapping, Tuple
import re
import smtplib

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

SoftwareDevFiles = Dict[str, Tuple[str, bytes]]

COMPLETION_REF = (2048, 1452)
EXPERIENCE_REF = (1165, 1555)
LOR_REF = (1165, 1556)

COMPLETION_PAGE = (842.0, 842.0 * COMPLETION_REF[1] / COMPLETION_REF[0])
EXPERIENCE_PAGE = (595.0, 595.0 * EXPERIENCE_REF[1] / EXPERIENCE_REF[0])
LOR_PAGE = (595.0, 595.0 * LOR_REF[1] / LOR_REF[0])

BLACK = colors.HexColor('#252525')
BLUE = colors.HexColor('#0755A4')
GOLD = colors.HexColor('#B99342')


def _register_fonts():
    candidates = {
        'Tinos': [
            r'C:\\Windows\\Fonts\\times.ttf',
            '/usr/share/fonts/truetype/croscore/Tinos-Regular.ttf',
            '/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf',
        ],
        'Tinos-Bold': [
            r'C:\\Windows\\Fonts\\timesbd.ttf',
            '/usr/share/fonts/truetype/croscore/Tinos-Bold.ttf',
            '/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf',
        ],
        'Arimo': [
            r'C:\\Windows\\Fonts\\arial.ttf',
            '/usr/share/fonts/truetype/croscore/Arimo-Regular.ttf',
            '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
        ],
        'Arimo-Bold': [
            r'C:\\Windows\\Fonts\\arialbd.ttf',
            '/usr/share/fonts/truetype/croscore/Arimo-Bold.ttf',
            '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf',
        ],
    }
    for name, paths in candidates.items():
        if name in pdfmetrics.getRegisteredFontNames():
            continue
        for path in paths:
            if Path(path).exists():
                pdfmetrics.registerFont(TTFont(name, path))
                break


_register_fonts()
SERIF = 'Tinos' if 'Tinos' in pdfmetrics.getRegisteredFontNames() else 'Times-Roman'
SERIF_BOLD = 'Tinos-Bold' if 'Tinos-Bold' in pdfmetrics.getRegisteredFontNames() else 'Times-Bold'
SANS = 'Arimo' if 'Arimo' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
SANS_BOLD = 'Arimo-Bold' if 'Arimo-Bold' in pdfmetrics.getRegisteredFontNames() else 'Helvetica-Bold'

try:
    pdfmetrics.registerFontFamily('Tinos', normal=SERIF, bold=SERIF_BOLD, italic=SERIF, boldItalic=SERIF_BOLD)
    pdfmetrics.registerFontFamily('Arimo', normal=SANS, bold=SANS_BOLD, italic=SANS, boldItalic=SANS_BOLD)
except Exception:
    pass


def _parse_date(value, fallback=None):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or '').strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%B %d, %Y', '%d %B %Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return fallback


def _date_long(value):
    d = _parse_date(value)
    return d.strftime('%B %-d, %Y') if d and hasattr(d, 'strftime') else str(value or '')


def _date_long_portable(value):
    d = _parse_date(value)
    if not d:
        return str(value or '')
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _date_ordinal(value):
    d = _parse_date(value)
    if not d:
        return str(value or '')
    suffix = 'th' if 10 < d.day % 100 < 14 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d.day % 10, 'th')
    return f"{d.day}{suffix} {d.strftime('%B %Y')}"


def _safe(value):
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '_', str(value or 'Candidate').strip())
    return cleaned.strip('_') or 'Candidate'


def _credential(name, end_date, supplied=''):
    supplied = re.sub(r'[^A-Za-z0-9-]', '', str(supplied or '').upper())
    if supplied:
        return supplied[:32]
    d = _parse_date(end_date, date.today())
    digest = sha256(f'{name}|software-developer-offline|{d.isoformat()}'.encode()).hexdigest()
    return f'APAR{d.strftime("%y%m")}{int(digest[:8], 16) % 10000:04d}'


def normalize_data(raw: Mapping) -> dict:
    name = str(raw.get('candidate_name') or raw.get('name') or '').strip()
    email = str(raw.get('email') or '').strip()
    start = _parse_date(raw.get('start_date'))
    end = _parse_date(raw.get('end_date'))
    issue = _parse_date(raw.get('issue_date'), date.today())
    if not name:
        raise ValueError('Candidate name is required.')
    if email and ('@' not in email or email.startswith('@') or email.endswith('@')):
        raise ValueError('Please enter a valid email address.')
    if not start or not end:
        raise ValueError('Start date and end date are required.')
    if end < start:
        raise ValueError('End date cannot be before start date.')
    return {
        'candidate_name': name,
        'first_name': name.split()[0],
        'email': email,
        'start_date': start,
        'end_date': end,
        'issue_date': issue,
        'role': str(raw.get('role') or 'Software Developer Intern').strip(),
        'domain': str(raw.get('domain') or 'Software Development').strip(),
        'mode': 'offline',
        'credential_id': _credential(name, end, raw.get('credential_id')),
    }


def _asset(base_dir, filename):
    return Path(base_dir) / 'static' / filename


def _draw_bg(c, base_dir, filename, page):
    p = _asset(base_dir, filename)
    if not p.exists():
        raise FileNotFoundError(f'Missing template: {p}')
    c.drawImage(ImageReader(str(p)), 0, 0, width=page[0], height=page[1], preserveAspectRatio=False, mask='auto')


def _scale(ref, page):
    return page[0] / ref[0], page[1] / ref[1]


def _rect_from_top(c, x, top, w, h, ref, page, fill=colors.white):
    sx, sy = _scale(ref, page)
    c.saveState()
    c.setFillColor(fill)
    c.setStrokeColor(fill)
    c.rect(x * sx, page[1] - (top + h) * sy, w * sx, h * sy, fill=1, stroke=0)
    c.restoreState()


def _text_left(c, text, x, y_from_top, font, size_px, ref, page, color=BLACK):
    sx, sy = _scale(ref, page)
    c.setFillColor(color)
    c.setFont(font, size_px * sx)
    c.drawString(x * sx, page[1] - y_from_top * sy, text)


def _text_center(c, text, x, y_from_top, font, size_px, ref, page, color=BLACK):
    sx, sy = _scale(ref, page)
    c.setFillColor(color)
    c.setFont(font, size_px * sx)
    c.drawCentredString(x * sx, page[1] - y_from_top * sy, text)


def _paragraph(c, html, x, top, width, ref, page, font, size_px, leading_px, align=TA_LEFT, color=BLACK):
    sx, sy = _scale(ref, page)
    style = ParagraphStyle(
        'overlay', fontName=font, fontSize=size_px * sx, leading=leading_px * sy,
        textColor=color, alignment=align, spaceAfter=0, spaceBefore=0,
    )
    p = Paragraph(html, style)
    w = width * sx
    _, h = p.wrap(w, page[1])
    p.drawOn(c, x * sx, page[1] - top * sy - h)
    return h


def build_software_dev_completion(data, base_dir):
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=COMPLETION_PAGE)
    c.setTitle('Software Developer Internship Completion Certificate')
    _draw_bg(c, base_dir, 'software_dev_completion_template_exact.png', COMPLETION_PAGE)

    # Remove only the variable content from the supplied reference while preserving its exact frame/header/signature/stamp.
    _rect_from_top(c, 690, 700, 700, 150, COMPLETION_REF, COMPLETION_PAGE, colors.HexColor('#F5F5F5'))
    _rect_from_top(c, 155, 852, 1740, 260, COMPLETION_REF, COMPLETION_PAGE, colors.HexColor('#F5F5F5'))
    _rect_from_top(c, 1450, 1160, 370, 100, COMPLETION_REF, COMPLETION_PAGE, colors.HexColor('#F5F5F5'))

    _text_center(c, data['candidate_name'], 1024, 790, SERIF, 68, COMPLETION_REF, COMPLETION_PAGE)
    body = (
        f"This is to certify that the individual has completed an internship with <b>Aparaitech Software</b> as a "
        f"<b>{data['role']}</b>. During the period from <b>{_date_long_portable(data['start_date'])} to "
        f"{_date_long_portable(data['end_date'])}</b>, they worked in <b>offline mode</b> and demonstrated strong "
        "technical skills, professionalism, discipline, and dedication to assigned responsibilities."
    )
    _paragraph(c, body, 190, 876, 1660, COMPLETION_REF, COMPLETION_PAGE, SANS, 29, 52, TA_CENTER)
    _text_left(c, f"Issued Date: {_date_long_portable(data['issue_date'])}", 1480, 1196, SANS_BOLD, 20, COMPLETION_REF, COMPLETION_PAGE)
    _text_left(c, f"Credential ID: {data['credential_id']}", 1480, 1230, SANS_BOLD, 20, COMPLETION_REF, COMPLETION_PAGE)

    c.showPage(); c.save()
    return out.getvalue()


def build_software_dev_experience(data, base_dir):
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=EXPERIENCE_PAGE)
    c.setTitle('Software Developer Internship Experience Letter')
    _draw_bg(c, base_dir, 'software_dev_experience_template_exact.png', EXPERIENCE_PAGE)

    # The uploaded design is retained exactly; only its sample date/name/body are replaced.
    _rect_from_top(c, 875, 450, 190, 65, EXPERIENCE_REF, EXPERIENCE_PAGE)
    _rect_from_top(c, 105, 590, 950, 600, EXPERIENCE_REF, EXPERIENCE_PAGE)

    _text_left(c, _date_long_portable(data['issue_date']), 910, 495, SANS, 20, EXPERIENCE_REF, EXPERIENCE_PAGE)
    _text_left(c, f"Dear {data['first_name']},", 140, 642, SANS_BOLD, 21, EXPERIENCE_REF, EXPERIENCE_PAGE)

    p1 = (
        f"This is to certify that <b>{data['candidate_name']}</b> has successfully completed a "
        f"<b>Software Developer Internship</b> at <b>Aparaitech Software</b> from "
        f"<b>{_date_ordinal(data['start_date'])} to {_date_ordinal(data['end_date'])}</b>."
    )
    p2 = "The internship was conducted <b>offline</b> at the company work location."
    p3 = (
        "During this period, the intern actively worked on real-time software development assignments, "
        "demonstrating technical skills, dedication, professional conduct, teamwork, and a willingness to learn. "
        "They gained practical exposure to development, debugging, testing, and project implementation."
    )
    p4 = "We appreciate their commitment and wish them all the best for their future professional endeavors."
    _paragraph(c, p1, 140, 710, 885, EXPERIENCE_REF, EXPERIENCE_PAGE, SANS, 21, 36)
    _paragraph(c, p2, 140, 835, 885, EXPERIENCE_REF, EXPERIENCE_PAGE, SANS, 21, 36)
    _paragraph(c, p3, 140, 900, 885, EXPERIENCE_REF, EXPERIENCE_PAGE, SANS, 21, 36)
    _paragraph(c, p4, 140, 1068, 885, EXPERIENCE_REF, EXPERIENCE_PAGE, SANS, 21, 36)

    c.saveState(); c.setFillAlpha(0); c.setFont('Helvetica', 1); c.drawString(2, 2, data['credential_id']); c.restoreState()
    c.showPage(); c.save()
    return out.getvalue()


def build_software_dev_lor(data, base_dir):
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=LOR_PAGE)
    c.setTitle('Software Developer Internship Letter of Recommendation')
    _draw_bg(c, base_dir, 'software_dev_lor_template_exact.png', LOR_PAGE)

    # Replace the sample/placeholder content while keeping the supplied LOR artwork, border, logo, stamp and signature.
    _rect_from_top(c, 95, 280, 980, 885, LOR_REF, LOR_PAGE)
    _rect_from_top(c, 95, 1200, 355, 190, LOR_REF, LOR_PAGE)

    _text_left(c, 'Aparaitech Software', 115, 320, SERIF, 22, LOR_REF, LOR_PAGE)
    _text_left(c, 'Baramati, Maharashtra 413102', 115, 355, SERIF, 22, LOR_REF, LOR_PAGE)
    _text_left(c, 'Email: info@aparaitechsoftware.org', 115, 390, SERIF, 21, LOR_REF, LOR_PAGE, BLUE)
    _text_left(c, f"Date: {_date_long_portable(data['issue_date'])}", 115, 430, SERIF, 21, LOR_REF, LOR_PAGE, BLUE)
    _text_left(c, 'To Whom It May Concern,', 115, 505, SERIF_BOLD, 22, LOR_REF, LOR_PAGE)

    p1 = (
        f"This letter is to formally recommend <b>{data['candidate_name']}</b>, who was associated with "
        f"<b>Aparaitech Software</b> as a <b>{data['role']}</b> and contributed to real-time industry projects "
        f"during an offline internship from <b>{_date_long_portable(data['start_date'])}</b> to "
        f"<b>{_date_long_portable(data['end_date'])}</b>."
    )
    p2 = (
        "During this period, the candidate demonstrated strong technical competence, analytical ability, and a professional "
        "approach toward software development. They participated in design, development, testing, debugging, and implementation "
        "of software applications and consistently showed a sound understanding of modern development practices."
    )
    p3 = (
        "In terms of work ethic, the candidate demonstrated dedication, responsibility, punctuality, and professionalism. "
        "Ownership of assigned tasks, adherence to deadlines, teamwork, and commitment to quality were evident throughout the internship."
    )
    p4 = (
        f"I strongly recommend <b>{data['candidate_name']}</b> and am confident that they will perform well in future academic "
        "and professional endeavors."
    )
    _paragraph(c, p1, 115, 560, 940, LOR_REF, LOR_PAGE, SERIF, 21, 31)
    _paragraph(c, p2, 115, 700, 940, LOR_REF, LOR_PAGE, SERIF, 21, 31)
    _paragraph(c, p3, 115, 870, 940, LOR_REF, LOR_PAGE, SERIF, 21, 31)
    _paragraph(c, p4, 115, 1015, 940, LOR_REF, LOR_PAGE, SERIF, 21, 31)

    _text_left(c, 'Sincerely,', 115, 1235, SERIF, 21, LOR_REF, LOR_PAGE)
    _text_left(c, 'Mr. Pratik Pawar', 115, 1270, SERIF_BOLD, 21, LOR_REF, LOR_PAGE, BLUE)
    _text_left(c, 'Assistant Team Leader', 115, 1305, SERIF, 21, LOR_REF, LOR_PAGE)
    _text_left(c, 'Aparaitech Software', 115, 1340, SERIF, 21, LOR_REF, LOR_PAGE)

    c.saveState(); c.setFillAlpha(0); c.setFont('Helvetica', 1); c.drawString(2, 2, data['credential_id']); c.restoreState()
    c.showPage(); c.save()
    return out.getvalue()


def build_software_developer_template_bundle(raw: Mapping, base_dir) -> Tuple[dict, SoftwareDevFiles]:
    data = normalize_data(raw)
    safe = _safe(data['candidate_name'])
    files: SoftwareDevFiles = {
        'completion': (f'{safe}_Software_Developer_Completion_Certificate.pdf', build_software_dev_completion(data, base_dir)),
        'experience': (f'{safe}_Software_Developer_Experience_Letter.pdf', build_software_dev_experience(data, base_dir)),
        'lor': (f'{safe}_Software_Developer_Letter_of_Recommendation.pdf', build_software_dev_lor(data, base_dir)),
    }
    return data, files


def send_software_developer_template_email(to_email, candidate_name, files: SoftwareDevFiles, smtp_config: Mapping):
    host = smtp_config.get('host') or smtp_config.get('SMTP_HOST')
    port = int(smtp_config.get('port') or smtp_config.get('SMTP_PORT') or 587)
    username = smtp_config.get('username') or smtp_config.get('user') or smtp_config.get('SMTP_USERNAME') or smtp_config.get('SMTP_USER')
    password = smtp_config.get('password') or smtp_config.get('pass') or smtp_config.get('SMTP_PASSWORD') or smtp_config.get('SMTP_PASS')
    sender = smtp_config.get('sender') or smtp_config.get('from') or smtp_config.get('SMTP_SENDER') or smtp_config.get('SMTP_FROM') or username
    if not host or not sender:
        raise ValueError('SMTP configuration is incomplete.')

    first = candidate_name.split()[0] if candidate_name else 'Candidate'
    msg = EmailMessage()
    msg['Subject'] = f'Software Developer Internship Documents – {candidate_name} | Aparaitech Software'
    msg['From'] = sender
    msg['To'] = to_email
    msg.set_content(
        f"Dear {first},\n\nCongratulations on completing your offline Software Developer Internship with Aparaitech Software.\n\n"
        "Please find attached your Completion Certificate, Internship Experience Letter, and Letter of Recommendation.\n\n"
        "Regards,\nTeam Aparaitech Software"
    )
    for _, (filename, payload) in files.items():
        msg.add_attachment(payload, maintype='application', subtype='pdf', filename=filename)

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        if username:
            server.login(username, password or '')
        server.send_message(msg)
