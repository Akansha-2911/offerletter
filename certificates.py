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
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Paragraph

CertificateFiles = Dict[str, Tuple[str, bytes]]

# Exact reference-image dimensions (pixels).
PROGRESS_REF = (1742, 1233)
EXPERIENCE_REF = (1153, 1534)
COMPLETION_REF = (2048, 1451)

# PDF page widths are chosen to keep the exact reference aspect ratio.
PROGRESS_PAGE = (842.0, 842.0 * PROGRESS_REF[1] / PROGRESS_REF[0])
EXPERIENCE_PAGE = (595.0, 595.0 * EXPERIENCE_REF[1] / EXPERIENCE_REF[0])
COMPLETION_PAGE = (842.0, 842.0 * COMPLETION_REF[1] / COMPLETION_REF[0])

CYAN = colors.HexColor('#12A9CF')
BLACK = colors.HexColor('#111111')


def _register_fonts():
    # Match the reference artwork as closely as possible on Windows,
    # while keeping Linux fallbacks for tests/deployment.
    candidates = {
        'Tinos': [r'C:\\Windows\\Fonts\\times.ttf', '/usr/share/fonts/truetype/croscore/Tinos-Regular.ttf', '/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf'],
        'Tinos-Bold': [r'C:\\Windows\\Fonts\\timesbd.ttf', '/usr/share/fonts/truetype/croscore/Tinos-Bold.ttf', '/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf'],
        'Arimo': [r'C:\\Windows\\Fonts\\arial.ttf', '/usr/share/fonts/truetype/croscore/Arimo-Regular.ttf', '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf'],
        'Arimo-Bold': [r'C:\\Windows\\Fonts\\arialbd.ttf', '/usr/share/fonts/truetype/croscore/Arimo-Bold.ttf', '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf'],
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
    return d.strftime('%B %d, %Y') if d else str(value or '')


def _date_ordinal(value):
    d = _parse_date(value)
    if not d:
        return str(value or '')
    suffix = 'th' if 10 < d.day % 100 < 14 else {1:'st',2:'nd',3:'rd'}.get(d.day % 10,'th')
    return f'{d.day}{suffix} {d.strftime("%B %Y")}'


def _filename_name(value):
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '_', str(value or 'Candidate').strip())
    return cleaned.strip('_') or 'Candidate'


def _credential_id(name, domain, end_date, supplied=''):
    supplied = re.sub(r'[^A-Za-z0-9-]', '', str(supplied or '').upper())
    if supplied:
        return supplied[:32]
    d = _parse_date(end_date, date.today())
    digest = sha256(f'{name}|{domain}|{d.isoformat()}'.encode()).hexdigest()
    return f'APAR{d.strftime("%y%m")}{int(digest[:8],16)%100000:05d}'


def normalize_certificate_data(raw: Mapping) -> dict:
    name = str(raw.get('candidate_name') or raw.get('name') or '').strip()
    email = str(raw.get('email') or '').strip()
    domain = str(raw.get('domain') or 'Software Development').strip()
    start = _parse_date(raw.get('start_date'))
    end = _parse_date(raw.get('end_date'))
    issue = _parse_date(raw.get('issue_date'), date.today())
    if not name:
        raise ValueError('Candidate name is required.')
    if not email or '@' not in email or email.startswith('@') or email.endswith('@'):
        raise ValueError('A valid candidate email is required.')
    if not start or not end:
        raise ValueError('Internship start date and end date are required.')
    if end < start:
        raise ValueError('Internship end date cannot be before the start date.')
    try:
        progress = max(0, min(100, int(float(raw.get('progress_percent', 100)))))
    except Exception:
        progress = 100
    try:
        months = max(1, min(60, int(float(raw.get('duration_months', 3)))))
    except Exception:
        months = 3
    return {
        'candidate_name': name,
        'first_name': name.split()[0],
        'email': email,
        'domain': domain,
        'start_date': start,
        'end_date': end,
        'issue_date': issue,
        'progress_percent': progress,
        'duration_months': months,
        'mode': str(raw.get('mode') or raw.get('location') or 'online').strip(),
        'verification_url': str(raw.get('verification_url') or 'lms.aparaitech.org').strip(),
        'credential_id': _credential_id(name, domain, end, raw.get('credential_id')),
    }


def _asset(base_dir, filename):
    return Path(base_dir) / 'static' / filename


def _draw_template(c, base_dir, filename, page_size):
    p = _asset(base_dir, filename)
    if not p.exists():
        raise FileNotFoundError(f'Missing certificate template: {p}')
    c.drawImage(ImageReader(str(p)), 0, 0, width=page_size[0], height=page_size[1], preserveAspectRatio=False, mask='auto')


def _xy(px, py_from_top, ref, page):
    sx = page[0] / ref[0]
    sy = page[1] / ref[1]
    return px * sx, page[1] - py_from_top * sy


def _font_px(px, ref, page):
    return px * (page[0] / ref[0])


def _fit(text, font, size, min_size, max_width):
    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= 0.25
    return size


def _draw_center(c, text, x_px, y_px, font, size_px, ref, page, max_width_px=None, color=BLACK):
    x, y = _xy(x_px, y_px, ref, page)
    size = _font_px(size_px, ref, page)
    if max_width_px:
        size = _fit(text, font, size, _font_px(18, ref, page), max_width_px * page[0] / ref[0])
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawCentredString(x, y, text)


def _draw_left(c, text, x_px, y_px, font, size_px, ref, page, color=BLACK):
    x, y = _xy(x_px, y_px, ref, page)
    c.setFont(font, _font_px(size_px, ref, page))
    c.setFillColor(color)
    c.drawString(x, y, text)


def _draw_right(c, text, x_px, y_px, font, size_px, ref, page, color=BLACK):
    x, y = _xy(x_px, y_px, ref, page)
    c.setFont(font, _font_px(size_px, ref, page))
    c.setFillColor(color)
    c.drawRightString(x, y, text)


def _paragraph_from_px(c, html, x_px, top_px, width_px, ref, page, font, size_px, leading_px, alignment=TA_LEFT):
    sx = page[0] / ref[0]
    sy = page[1] / ref[1]
    x = x_px * sx
    top = page[1] - top_px * sy
    width = width_px * sx
    style = ParagraphStyle(
        'exact', fontName=font, fontSize=size_px*sx, leading=leading_px*sy,
        textColor=BLACK, alignment=alignment, spaceAfter=0, spaceBefore=0,
    )
    p = Paragraph(html, style)
    _, h = p.wrap(width, page[1])
    p.drawOn(c, x, top-h)
    return h


def _metadata(c, title, data):
    c.setTitle(title)
    c.setAuthor('Aparaitech Software')
    c.setSubject(f"{title} - {data['candidate_name']} - {data['credential_id']}")


# -------------------- PROGRESS CERTIFICATE --------------------
def build_progress_certificate(data, base_dir):
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=PROGRESS_PAGE)
    _metadata(c, 'Progress Certificate', data)
    _draw_template(c, base_dir, 'progress_template_exact.png', PROGRESS_PAGE)

    # Positions are traced directly from the approved reference image.
    _draw_center(c, data['domain'], 871, 535, SERIF, 78, PROGRESS_REF, PROGRESS_PAGE, max_width_px=980)
    _draw_center(c, data['candidate_name'], 871, 765, SERIF, 82, PROGRESS_REF, PROGRESS_PAGE, max_width_px=980)

    sentence = f"In recognition of successfully reaching the {data['progress_percent']}% milestone in the Live Project."
    _draw_center(c, sentence, 871, 860, SERIF, 29, PROGRESS_REF, PROGRESS_PAGE, max_width_px=1080)
    _draw_center(c, _date_long(data['issue_date']), 871, 952, SERIF, 26, PROGRESS_REF, PROGRESS_PAGE, max_width_px=340)
    # Footer — matched to the approved progress-certificate reference.
    _draw_left(c, f"Creditional ID: {data['credential_id']}", 418, 1140, SERIF, 22, PROGRESS_REF, PROGRESS_PAGE)
    _draw_left(c, f"Certification Verification : {data['verification_url']}", 1046, 1140, SERIF, 21, PROGRESS_REF, PROGRESS_PAGE)

    # Thin vertical divider exactly between the two footer blocks.
    sx = PROGRESS_PAGE[0] / PROGRESS_REF[0]
    sy = PROGRESS_PAGE[1] / PROGRESS_REF[1]
    divider_x = 896 * sx
    divider_top = PROGRESS_PAGE[1] - 1119 * sy
    divider_bottom = PROGRESS_PAGE[1] - 1161 * sy
    c.saveState()
    c.setStrokeColor(colors.HexColor('#777777'))
    c.setLineWidth(1.0 * sx)
    c.line(divider_x, divider_bottom, divider_x, divider_top)
    c.restoreState()

    c.showPage(); c.save()
    return out.getvalue()


# -------------------- EXPERIENCE LETTER --------------------
def build_experience_letter(data, base_dir):
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=EXPERIENCE_PAGE)
    _metadata(c, 'Internship Experience Letter', data)
    _draw_template(c, base_dir, 'experience_template_exact.png', EXPERIENCE_PAGE)

    _draw_right(c, _date_long(data['issue_date']), 1030, 489, SANS, 20, EXPERIENCE_REF, EXPERIENCE_PAGE)
    _draw_left(c, f"Dear {data['first_name']},", 125, 626, SANS_BOLD, 20, EXPERIENCE_REF, EXPERIENCE_PAGE)

    mode = data['mode'].lower()
    body1 = (
        f"This is to certify that the student has completed a <b>{data['duration_months']}-months Live Project Internship Program</b> "
        f"in the domain of <b>{data['domain']} at Aparaitech Software</b> from <b>{_date_ordinal(data['start_date'])} to {_date_ordinal(data['end_date'])}.</b>"
    )
    body2 = f"The internship was conducted <b>{mode}</b>."
    body3 = (
        f"During this period, the student actively worked on real-time projects, demonstrating strong technical skills, dedication, and a willingness to learn. "
        f"They gained practical experience in <b>{data['domain']}</b> concepts and contributed effectively to assigned tasks."
    )
    body4 = "We appreciate their commitment and wish them all the best for their future endeavors."

    _paragraph_from_px(c, body1, 124, 681, 900, EXPERIENCE_REF, EXPERIENCE_PAGE, SANS, 22, 36)
    _paragraph_from_px(c, body2, 124, 824, 900, EXPERIENCE_REF, EXPERIENCE_PAGE, SANS, 22, 36)
    _paragraph_from_px(c, body3, 124, 895, 900, EXPERIENCE_REF, EXPERIENCE_PAGE, SANS, 22, 36)
    _paragraph_from_px(c, body4, 124, 1070, 900, EXPERIENCE_REF, EXPERIENCE_PAGE, SANS, 22, 36)

    # Keep credential searchable for existing app/tests without changing the approved visual layout.
    c.saveState(); c.setFillColor(colors.white); c.setFont(SANS, 1)
    c.drawString(2, 2, f"{data['candidate_name']} {data['credential_id']}")
    c.restoreState()

    c.showPage(); c.save()
    return out.getvalue()


# -------------------- COMPLETION CERTIFICATE --------------------
def build_completion_certificate(data, base_dir):
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=COMPLETION_PAGE)
    _metadata(c, 'Certificate of Completion', data)
    _draw_template(c, base_dir, 'completion_template_exact.png', COMPLETION_PAGE)

    _draw_left(c, data['candidate_name'], 355, 750, SERIF, 88, COMPLETION_REF, COMPLETION_PAGE)

    line1 = (
        f"This certificate recognizes the successful completion of a <b>{data['duration_months']}-month real-world live project</b> in the domain of "
        f"<b>{data['domain']} at Aparaitech Software.</b>"
    )
    line2 = (
        "During this period, the candidate gained <b>practical experience</b> and demonstrated strong commitment while working on "
        "<b>industry-oriented projects.</b>"
    )
    _paragraph_from_px(c, line1, 355, 835, 1360, COMPLETION_REF, COMPLETION_PAGE, SERIF, 32, 44)
    _paragraph_from_px(c, line2, 355, 965, 1360, COMPLETION_REF, COMPLETION_PAGE, SERIF, 32, 44)

    _draw_left(c, f"Credential ID : {data['credential_id']}", 1570, 1340, SERIF, 22, COMPLETION_REF, COMPLETION_PAGE)
    _draw_left(c, f"Date : {_date_long(data['issue_date'])}", 1570, 1370, SERIF, 22, COMPLETION_REF, COMPLETION_PAGE)

    c.showPage(); c.save()
    return out.getvalue()


def build_certificate_bundle(raw: Mapping, base_dir) -> Tuple[dict, CertificateFiles]:
    data = normalize_certificate_data(raw)
    safe = _filename_name(data['candidate_name'])
    files: CertificateFiles = {
        'experience': (f'{safe}_Experience_Letter.pdf', build_experience_letter(data, base_dir)),
        'progress': (f'{safe}_Progress_Certificate.pdf', build_progress_certificate(data, base_dir)),
        'completion': (f'{safe}_Completion_Certificate.pdf', build_completion_certificate(data, base_dir)),
    }
    return data, files


def send_certificate_bundle_email(
    to_email,
    candidate_name,
    files: CertificateFiles,
    smtp_config: Mapping,
    domain="Live Project"
):
    host = smtp_config.get('host') or smtp_config.get('SMTP_HOST')
    port = int(smtp_config.get('port') or smtp_config.get('SMTP_PORT') or 587)

    username = (
        smtp_config.get('username')
        or smtp_config.get('SMTP_USERNAME')
        or smtp_config.get('SMTP_USER')
    )

    password = (
        smtp_config.get('password')
        or smtp_config.get('SMTP_PASSWORD')
        or smtp_config.get('SMTP_PASS')
    )

    sender = (
        smtp_config.get('sender')
        or smtp_config.get('SMTP_SENDER')
        or smtp_config.get('SMTP_FROM')
        or username
    )

    use_tls = smtp_config.get('use_tls', True)

    if not host or not sender:
        raise ValueError('SMTP configuration is incomplete.')

    first_name = candidate_name.split()[0] if candidate_name else "Student"

    msg = EmailMessage()

    msg['Subject'] = (
        f"Congratulations {candidate_name} – "
        f"Live Project Program Certificates | Aparaitech Software"
    )

    msg['From'] = sender
    msg['To'] = to_email

    email_body = f"""Dear {first_name},

Greetings from Aparaitech Software!

🎉 Congratulations on successfully completing the 3-month Live Project Program in the {domain} domain!

Your dedication, consistency, and hard work throughout the program are truly appreciated.

We are pleased to share the following documents with you:

• Progress Certificate – Recognizing the milestones achieved during your Live Project Program.

• Completion Certificate – Awarded for successfully completing the Live Project Program.

• Internship Experience Letter – Recognizing your active involvement in real-time projects and the practical experience gained during the program.

These documents represent your commitment to gaining real-world experience and developing strong, industry-relevant skills.

We hope this learning journey has enhanced your technical knowledge, practical skills, and confidence in working on real-time {domain} projects.

Keep exploring, keep building, and continue striving for excellence.

📎 Kindly find the attached documents for your reference.

If you have any queries or require further assistance, please feel free to reach out to us.

Once again, congratulations on your achievement, and best wishes for your future endeavors! 🚀

Regards,

Team Aparaitech Software
Aparaitech – Software & AI Company
📍 Baramati, Pune
📞 +91 9158852129
🌐 www.aparaitech.org
"""

    msg.set_content(email_body)

    for _, (filename, payload) in files.items():
        msg.add_attachment(
            payload,
            maintype='application',
            subtype='pdf',
            filename=filename
        )
    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.ehlo()

            if use_tls:
                server.starttls()
                server.ehlo()

            if username:
                server.login(username, password or '')

            server.send_message(msg)

    except Exception as exc:
        raise RuntimeError(f"SMTP email sending failed: {exc}") from exc
