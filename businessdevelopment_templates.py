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

BusinessDevFiles = Dict[str, Tuple[str, bytes]]

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
    digest = sha256(f'{name}|business-development-offline|{d.isoformat()}'.encode()).hexdigest()
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
        'role': str(raw.get('role') or 'Business Development Intern').strip(),
        'domain': str(raw.get('domain') or 'Business Development').strip(),
        'mode': 'offline',
        'location': 'Baramati, Pune',
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


def build_bd_completion(data, base_dir):
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=COMPLETION_PAGE)
    c.setTitle('Business Development Internship Completion Certificate')
    _draw_bg(c, base_dir, 'software_dev_completion_template_exact.png', COMPLETION_PAGE)

    # Remove variable content while preserving frame, header, signature, and stamp.
    _rect_from_top(c, 690, 700, 700, 150, COMPLETION_REF, COMPLETION_PAGE, colors.HexColor('#F5F5F5'))
    _rect_from_top(c, 155, 852, 1740, 260, COMPLETION_REF, COMPLETION_PAGE, colors.HexColor('#F5F5F5'))
    _rect_from_top(c, 1450, 1160, 370, 100, COMPLETION_REF, COMPLETION_PAGE, colors.HexColor('#F5F5F5'))

    _text_center(c, data['candidate_name'], 1024, 790, SERIF, 68, COMPLETION_REF, COMPLETION_PAGE)
    body = (
        f"This is to certify that the individual has completed an internship with <b>Aparaitech Software</b> as a "
        f"<b>{data['role']}</b>. During the period from <b>{_date_long_portable(data['start_date'])} to "
        f"{_date_long_portable(data['end_date'])}</b>, they worked in <b>offline mode</b> at our <b>Baramati, Pune</b> office "
        "and demonstrated strong communication skills, strategic market outreach, professionalism, discipline, and dedication to assigned responsibilities."
    )
    _paragraph(c, body, 190, 876, 1660, COMPLETION_REF, COMPLETION_PAGE, SANS, 29, 52, TA_CENTER)
    _text_left(c, f"Issued Date: {_date_long_portable(data['issue_date'])}", 1480, 1196, SANS_BOLD, 20, COMPLETION_REF, COMPLETION_PAGE)
    _text_left(c, f"Credential ID: {data['credential_id']}", 1480, 1230, SANS_BOLD, 20, COMPLETION_REF, COMPLETION_PAGE)

    c.showPage(); c.save()
    return out.getvalue()


def build_bd_experience(data, base_dir):
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=EXPERIENCE_PAGE)
    c.setTitle('Business Development Internship Experience Letter')
    _draw_bg(c, base_dir, 'software_dev_experience_template_exact.png', EXPERIENCE_PAGE)

    _rect_from_top(c, 875, 450, 190, 65, EXPERIENCE_REF, EXPERIENCE_PAGE)
    _rect_from_top(c, 105, 590, 950, 600, EXPERIENCE_REF, EXPERIENCE_PAGE)

    _text_left(c, _date_long_portable(data['issue_date']), 910, 495, SANS, 20, EXPERIENCE_REF, EXPERIENCE_PAGE)
    _text_left(c, f"Dear {data['first_name']},", 140, 642, SANS_BOLD, 21, EXPERIENCE_REF, EXPERIENCE_PAGE)

    p1 = (
        f"This is to certify that <b>{data['candidate_name']}</b> has successfully completed a "
        f"<b>Business Development Internship</b> at <b>Aparaitech Software</b> from "
        f"<b>{_date_ordinal(data['start_date'])} to {_date_ordinal(data['end_date'])}</b>."
    )
    p2 = "The internship was conducted <b>offline</b> at the company work location in <b>Baramati, Pune</b>."
    p3 = (
        "During this period, the intern actively contributed to lead generation, market analysis, client outreach, "
        "strategic business communications, and corporate development assignments. They demonstrated strong commercial awareness, "
        "persuasive communication, dedication, professional conduct, teamwork, and an exceptional drive to learn."
    )
    p4 = "We appreciate their commitment and valuable contribution to Aparaitech Software and wish them all the best for their future professional endeavors."
    _paragraph(c, p1, 140, 710, 885, EXPERIENCE_REF, EXPERIENCE_PAGE, SANS, 21, 36)
    _paragraph(c, p2, 140, 835, 885, EXPERIENCE_REF, EXPERIENCE_PAGE, SANS, 21, 36)
    _paragraph(c, p3, 140, 900, 885, EXPERIENCE_REF, EXPERIENCE_PAGE, SANS, 21, 36)
    _paragraph(c, p4, 140, 1068, 885, EXPERIENCE_REF, EXPERIENCE_PAGE, SANS, 21, 36)

    c.saveState(); c.setFillAlpha(0); c.setFont('Helvetica', 1); c.drawString(2, 2, data['credential_id']); c.restoreState()
    c.showPage(); c.save()
    return out.getvalue()


def build_bd_lor(data, base_dir):
    out = BytesIO()
    c = canvas.Canvas(out, pagesize=LOR_PAGE)
    c.setTitle('Business Development Internship Letter of Recommendation')
    _draw_bg(c, base_dir, 'software_dev_lor_template_exact.png', LOR_PAGE)

    _rect_from_top(c, 95, 280, 980, 885, LOR_REF, LOR_PAGE)
    _rect_from_top(c, 95, 1200, 355, 190, LOR_REF, LOR_PAGE)

    _text_left(c, 'Aparaitech Software', 115, 320, SERIF, 22, LOR_REF, LOR_PAGE)
    _text_left(c, 'Baramati, Pune, Maharashtra 413102', 115, 355, SERIF, 22, LOR_REF, LOR_PAGE)
    _text_left(c, 'Email: info@ai.aparaitech.org', 115, 390, SERIF, 21, LOR_REF, LOR_PAGE, BLUE)
    _text_left(c, f"Date: {_date_long_portable(data['issue_date'])}", 115, 430, SERIF, 21, LOR_REF, LOR_PAGE, BLUE)
    _text_left(c, 'To Whom It May Concern,', 115, 505, SERIF_BOLD, 22, LOR_REF, LOR_PAGE)

    p1 = (
        f"This letter is to formally recommend <b>{data['candidate_name']}</b>, who was associated with "
        f"<b>Aparaitech Software</b> as a <b>{data['role']}</b> and contributed to business development and corporate "
        f"outreach initiatives during an offline internship from <b>{_date_long_portable(data['start_date'])}</b> to "
        f"<b>{_date_long_portable(data['end_date'])}</b> at our Baramati, Pune office."
    )
    p2 = (
        "During this period, the candidate demonstrated outstanding communication abilities, strategic acumen, and a proactive "
        "approach toward lead identification, market research, and client relationship building. They consistently engaged with "
        "prospective clients, supported outreach campaigns, and exhibited a sound understanding of modern corporate outreach strategies."
    )
    p3 = (
        "In terms of work ethic, the candidate demonstrated dedication, responsibility, punctuality, and high integrity. "
        "Ownership of assigned targets, adherence to deadlines, active teamwork, and a relentless commitment to organizational goals "
        "were evident throughout their internship."
    )
    p4 = (
        f"I strongly recommend <b>{data['candidate_name']}</b> and am confident that they will excel in and bring great value "
        "to future academic and professional endeavors."
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


def build_business_development_template_bundle(raw: Mapping, base_dir) -> Tuple[dict, BusinessDevFiles]:
    data = normalize_data(raw)
    safe = _safe(data['candidate_name'])
    files: BusinessDevFiles = {
        'completion': (f'{safe}_Business_Development_Completion_Certificate.pdf', build_bd_completion(data, base_dir)),
        'experience': (f'{safe}_Business_Development_Experience_Letter.pdf', build_bd_experience(data, base_dir)),
        'lor': (f'{safe}_Business_Development_Letter_of_Recommendation.pdf', build_bd_lor(data, base_dir)),
    }
    return data, files


def send_business_development_template_email(to_email, candidate_name, files: BusinessDevFiles, smtp_config: Mapping, data: Mapping | None = None):
    host = smtp_config.get('host') or smtp_config.get('SMTP_HOST') or 'smtp.gmail.com'
    port = int(smtp_config.get('port') or smtp_config.get('SMTP_PORT') or 587)
    username = (
        smtp_config.get('username')
        or smtp_config.get('user')
        or smtp_config.get('SMTP_USERNAME')
        or smtp_config.get('SMTP_USER')
    )
    password = (
        smtp_config.get('password')
        or smtp_config.get('pass')
        or smtp_config.get('SMTP_PASSWORD')
        or smtp_config.get('SMTP_PASS')
    )
    sender = (
        smtp_config.get('sender')
        or smtp_config.get('from')
        or smtp_config.get('SMTP_SENDER')
        or smtp_config.get('SMTP_FROM')
        or username
    )

    if not host or not sender:
        raise ValueError('SMTP configuration is incomplete.')
    if not username or not password:
        raise ValueError('SMTP credentials (username/password) are missing.')

    data = dict(data or {})
    first = candidate_name.split()[0] if candidate_name else 'Candidate'
    start_date = _date_long_portable(data.get('start_date')) if data.get('start_date') else ''
    end_date = _date_long_portable(data.get('end_date')) if data.get('end_date') else ''
    credential_id = str(data.get('credential_id') or '').strip()
    duration_line = f'Internship Duration: {start_date} to {end_date}' if start_date and end_date else ''

    msg = EmailMessage()
    msg['Subject'] = f'Congratulations on Successfully Completing Your Business Development Internship | Aparaitech Software'
    msg['From'] = sender
    msg['To'] = to_email

    plain_lines = [
        f'Dear {first},', '', 'Congratulations!', '',
        'We are pleased to congratulate you on the successful completion of your Offline Business Development Internship with Aparaitech Software at our Baramati, Pune office.'
    ]
    if duration_line:
        plain_lines.extend(['', duration_line])
    plain_lines.extend([
        '',
        'During your internship, you demonstrated commitment, professionalism, market acumen, and dedication while contributing to assigned business development and outreach initiatives.',
        '',
        'As recognition of your successful internship completion, we have attached the following official documents:',
        '1. Certificate of Completion',
        '2. Internship Experience Letter',
        '3. Letter of Recommendation',
        '',
        'Please keep these documents safely for your academic and professional records.'
    ])
    if credential_id:
        plain_lines.extend(['', f'Credential ID: {credential_id}'])
    plain_lines.extend([
        '',
        'We appreciate your contribution and wish you continued success in your future academic and professional journey.',
        '', 'Best Regards,', 'Team Aparaitech Software', 'Aparaitech Software Company', 'Baramati, Pune', 'Email: info@ai.aparaitech.org'
    ])
    msg.set_content('\n'.join(plain_lines))

    duration_html = f'<p style="margin:0 0 16px"><strong>Internship Duration:</strong> {start_date} to {end_date}</p>' if duration_line else ''
    credential_html = f'<p style="margin:18px 0 0"><strong>Credential ID:</strong> {credential_id}</p>' if credential_id else ''
    html = f'''<!doctype html>
<html><body style="font-family:Arial,Helvetica,sans-serif;background:#f6f8fb;margin:0;padding:24px;color:#1f2937">
<div style="max-width:680px;margin:auto;background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
<div style="background:#176b3a;color:#fff;padding:22px 28px"><div style="font-size:21px;font-weight:700">Aparaitech Software</div><div style="font-size:13px;opacity:.9;margin-top:4px">Business Development Internship Completion</div></div>
<div style="padding:30px 28px;line-height:1.65">
<p>Dear <strong>{first}</strong>,</p>
<h2 style="color:#176b3a;margin:6px 0 14px">Congratulations on successfully completing your internship!</h2>
<p>We are pleased to congratulate you on the successful completion of your <strong>Offline Business Development Internship</strong> with <strong>Aparaitech Software</strong> at our <strong>Baramati, Pune</strong> office.</p>
{duration_html}
<p>During your internship, you demonstrated commitment, professionalism, client relationship skills, and dedication while contributing to key business development and outreach initiatives.</p>
<p>As recognition of your successful internship completion, the following official documents are attached to this email:</p>
<div style="background:#f0f9f4;border-left:4px solid #176b3a;padding:14px 18px;margin:16px 0"><div>Certificate of Completion</div><div>Internship Experience Letter</div><div>Letter of Recommendation</div></div>
<p>Please keep these documents safely for your academic and professional records.</p>
{credential_html}
<p style="margin-top:22px">We appreciate your contribution and wish you continued success in your future academic and professional journey.</p>
<p style="margin-bottom:0">Best Regards,<br><strong>Team Aparaitech Software</strong><br>Aparaitech Software Company<br>Baramati, Pune<br>Email: info@ai.aparaitech.org</p>
</div></div></body></html>'''
    msg.add_alternative(html, subtype='html')

    for _, (filename, payload) in files.items():
        msg.add_attachment(payload, maintype='application', subtype='pdf', filename=filename)

    # Resilient SMTP delivery: Try 587 STARTTLS, with automatic fallback to 465 SSL
    server = None
    sent = False
    last_err = None

    # Try Primary
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
        server.login(username, password)
        server.send_message(msg)
        sent = True
    except (smtplib.SMTPServerDisconnected, TimeoutError, OSError) as exc:
        last_err = exc
    finally:
        if server:
            try: server.quit()
            except Exception:
                try: server.close()
                except Exception: pass
            server = None

    # Fallback to SSL port 465 if primary connection failed or disconnected
    if not sent:
        try:
            server = smtplib.SMTP_SSL(host, 465, timeout=30)
            server.login(username, password)
            server.send_message(msg)
            sent = True
        except Exception as exc:
            raise RuntimeError(f"Email delivery failed (tried {port} and 465): {exc}") from (last_err or exc)
        finally:
            if server:
                try: server.quit()
                except Exception:
                    try: server.close()
                    except Exception: pass
