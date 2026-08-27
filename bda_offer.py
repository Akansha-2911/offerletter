from __future__ import annotations

import io
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle, Flowable

W, H = A4
DARK = colors.HexColor('#0d2b5e')
CYAN = colors.HexColor('#00aec7')
GREY = colors.HexColor('#555555')
IST = ZoneInfo('Asia/Kolkata')


def _now_ist():
    """Return current India Standard Time (Asia/Kolkata)."""
    return datetime.now(IST)


def _gp(base_dir, filename):
    return os.path.join(base_dir, 'static', filename)


def _fmt_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').strftime('%d %B %Y')
    except Exception:
        return value or ''


def _draw_page(c, doc, base_dir):
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(CYAN)
    c.rect(0, H - 92, W, 4, fill=1, stroke=0)

    logo = _gp(base_dir, 'logo.png')
    if os.path.exists(logo):
        c.drawImage(logo, 14, H - 80, width=80, height=60,
                    preserveAspectRatio=True, mask='auto')

    c.setFillColor(DARK)
    c.setFont('Helvetica-Bold', 17)
    c.drawRightString(W - 30, H - 46, 'APARAITECH SOFTWARE COMPANY')
    c.setFont('Helvetica', 9)
    c.setFillColor(CYAN)
    c.drawRightString(W - 30, H - 62, 'We Build Your Vision')

    c.setStrokeColor(CYAN)
    c.setLineWidth(1)
    c.line(40, 52, W - 40, 52)
    c.setFont('Helvetica', 7.5)
    c.setFillColor(GREY)
    c.drawCentredString(
        W / 2, 38,
        'Baramati, Pune - 413102, Maharashtra  |  '
        'info@ai.aparaitech.org  |  www.aparaitech.org'
    )
    c.setFont('Helvetica', 8)
    c.drawRightString(W - 40, 20, f'Page {doc.page}')
    c.restoreState()


def _draw_watermark(c, admin_user, timestamp, base_dir):
    logo_path = _gp(base_dir, 'logo.png')
    if not os.path.exists(logo_path):
        return

    c.saveState()
    c.translate(W / 2, H / 2)
    c.rotate(30)
    try:
        c.setFillAlpha(0.12)
        c.setStrokeAlpha(0.12)
    except Exception:
        pass

    c.drawImage(
        logo_path, -250, -150, width=500, height=360,
        preserveAspectRatio=True, mask='auto'
    )
    c.setFont('Helvetica-Bold', 13)
    c.drawCentredString(0, -190, f'GEN BY: {admin_user.upper()}')
    c.setFont('Helvetica', 9)
    c.drawCentredString(0, -206, timestamp)
    c.setFont('Helvetica-Bold', 11)
    c.drawCentredString(0, -224, 'APARAITECH CONFIDENTIAL')
    c.restoreState()


class _SignatureBlock(Flowable):
    def __init__(self, sig_path, stamp_path):
        super().__init__()
        self.sig_path = sig_path
        self.stamp_path = stamp_path
        self.width = 4 * inch
        self.height = 1.55 * inch

    def draw(self):
        c = self.canv
        if self.sig_path and os.path.exists(self.sig_path):
            c.drawImage(
                self.sig_path, 0, 0.92 * inch,
                width=1.5 * inch, height=0.58 * inch,
                preserveAspectRatio=True, mask='auto'
            )
        if self.stamp_path and os.path.exists(self.stamp_path):
            c.drawImage(
                self.stamp_path, 1.52 * inch, 0.62 * inch,
                width=1.0 * inch, height=1.0 * inch,
                preserveAspectRatio=True, mask='auto'
            )
        c.setFont('Courier', 7.8)
        c.setFillColor(GREY)
        c.drawString(0, 0.55 * inch, 'Digitally Signed by')
        c.drawString(0, 0.40 * inch,
                     f"Date: {_now_ist().strftime('%d-%m-%Y %H:%M')}")
        c.setFont('Helvetica-Bold', 9)
        c.setFillColor(DARK)
        c.drawString(0, 0.20 * inch, 'Managing Director')


def build_bda_pdf(data, base_dir, admin_user='ADMIN',
                  owner_password='change-me-in-env'):
    """Generate a Business Development Associate offer letter PDF."""
    buf = io.BytesIO()

    body = ParagraphStyle(
        'bda-body', fontSize=9.4, fontName='Helvetica', leading=13,
        textColor=colors.black, alignment=TA_JUSTIFY, spaceAfter=4
    )
    bold = ParagraphStyle(
        'bda-bold', fontSize=9.5, fontName='Helvetica-Bold', leading=13,
        textColor=DARK, spaceAfter=2
    )
    title = ParagraphStyle(
        'bda-title', fontSize=13, fontName='Helvetica-Bold',
        textColor=DARK, alignment=TA_CENTER, spaceAfter=8
    )
    rgt = ParagraphStyle(
        'bda-right', fontSize=9.3, fontName='Helvetica',
        textColor=colors.black, alignment=TA_RIGHT
    )

    def sec(n, head, text):
        return KeepTogether([
            Paragraph(f'<b>{n}. {head}</b>', bold),
            Paragraph(text, body),
            Spacer(1, 4),
        ])

    employee_name = (data.get('employee_name') or 'Candidate').strip()
    email = (data.get('email') or '').strip()
    joining = _fmt_date(data.get('joining_date', ''))
    end_date = _fmt_date(data.get('training_end_date', ''))
    monthly_target = (
        data.get('monthly_target')
        or 'As assigned by the Business Development Head'
    ).strip()
    reporting_to = (
        data.get('reporting_to')
        or 'Business Development Head / Management'
    ).strip()
    work_mode = (
        data.get('work_mode')
        or 'On-site / Hybrid as per business requirement'
    ).strip()

    ref = f"APC/HRD/{_now_ist().strftime('%Y')}/BDA-OFF-{_now_ist().strftime('%m%d%H%M')}"
    date_str = _now_ist().strftime('%d %B %Y')
    watermark_ts = _now_ist().strftime('%d-%m-%Y %H:%M:%S')

    story = []

    top = Table(
        [[
            Paragraph(f'<b>Ref:</b> {ref}', body),
            Paragraph(f'<b>Date:</b> {date_str}', rgt)
        ]],
        colWidths=[255, 255],
        hAlign='LEFT'
    )
    top.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (-1, -1), (-1, -1), 0)
    ]))
    story.extend([top, Spacer(1, 8)])

    story.append(Paragraph(
        'BUSINESS DEVELOPMENT ASSOCIATE - OFFER LETTER', title
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph('To,', body))
    story.append(Paragraph(f'<b>Mr./Ms. {employee_name}</b>', bold))

    if data.get('college'):
        story.append(Paragraph(str(data.get('college')), body))
    if data.get('department'):
        story.append(Paragraph(
            f"Department: {data.get('department')}", body
        ))

    story.append(Paragraph('Maharashtra, India', body))
    if email:
        story.append(Paragraph(f'<b>Email:</b> {email}', body))

    story.append(Spacer(1, 6))
    story.append(Paragraph(
        '<b>Subject: Offer for the position of Business Development Associate (BDA)</b>',
        body
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f'Dear {employee_name},', body))

    story.append(Paragraph(
        'We are pleased to offer you the position of '
        '<b>Business Development Associate (BDA)</b> at '
        '<b>APARAITECH SOFTWARE COMPANY</b>. Your role will focus on '
        'business growth, lead generation, candidate/client communication, '
        'follow-ups, conversion support, relationship management, and '
        'achievement of assigned business targets.',
        body
    ))
    story.append(Spacer(1, 5))

    story.append(sec(
        '1', 'Position &amp; Reporting',
        f'You are appointed as <b>Business Development Associate (BDA)</b> '
        f'and will report to <b>{reporting_to}</b>. Your work mode will be '
        f'<b>{work_mode}</b>. You may be assigned campaigns, territories, '
        'lead pools, institutions, clients, or business-development '
        'activities depending on organizational requirements.'
    ))

    story.append(sec(
        '2', 'Joining / Training Period',
        f'&#x2022; <b>Joining Date:</b> {joining}<br/>'
        f'&#x2022; <b>Training / Review End Date:</b> {end_date}<br/>'
        'The initial period will be treated as a training/probation and '
        'performance-evaluation period. Continuation will depend on '
        'discipline, attendance, reporting, communication quality, and '
        'target performance.'
    ))

    story.append(sec(
        '3', 'Roles &amp; Responsibilities',
        '&#x2022; Generate and qualify business leads through approved channels.<br/>'
        '&#x2022; Conduct professional calls, messages, follow-ups, and '
        'candidate/client coordination.<br/>'
        '&#x2022; Maintain accurate daily reports, lead status, follow-up '
        'history, and conversion records.<br/>'
        '&#x2022; Support campaigns, institutional outreach, recruitment/'
        'internship drives, and service promotion.<br/>'
        '&#x2022; Meet assigned daily, weekly, monthly, and campaign-specific '
        'business targets.<br/>'
        '&#x2022; Maintain professional conduct and protect confidential '
        'business and customer information.'
    ))

    story.append(sec(
        '4', 'Target-Based Stipend &amp; Incentive Structure',
        'This is a <b>target-linked performance role</b>. The stipend / '
        'incentive payable to you will be determined on the basis of '
        'verified target achievement, conversion quality, consistency, '
        'attendance, reporting discipline, and management evaluation.<br/><br/>'
        '<b>Stipend: Up to 15,000 per month</b>, based on achievement of '
        'applicable targets and performance as per the company incentive '
        'policy. The stipend is performance-linked and is not a fixed or '
        'guaranteed amount.<br/><br/>'
        '<b>Note:</b> Upon successfully completing the training period and '
        'meeting the required performance standards, you may be considered '
        'for a <b>full-time employment opportunity</b> with the company. '
        'The full-time position may offer a <b>CTC of up to 4.5 LPA to 5 LPA</b>, '
        'subject to performance, eligibility, role requirements, management '
        'evaluation, and company policies. The company reserves the right '
        'to determine the final CTC and employment terms based on individual '
        'performance, business needs, and organizational considerations.'
    ))

    story.append(sec(
        '5', 'Business Targets &amp; Performance Review',
        f'<b>Current Target Framework:</b> {monthly_target}. Targets may be '
        'assigned daily, weekly, monthly, campaign-wise, or conversion-wise. '
        'The company may revise targets depending on business requirements, '
        'market conditions, campaign quality, and role responsibilities. '
        'Only verified and eligible conversions will be considered for '
        'target achievement and incentives.'
    ))

    # Requested additional points, matching the provided format.
    story.append(sec(
        '6', 'Working Hours &amp; Attendance',
        'The company follows a <b>6-day work week (9 hours/day)</b>, '
        '<b>Monday through Saturday, 10:00 AM to 7:30 PM</b>. You may be '
        'required to work additional hours during critical project phases '
        'or business requirements. Regular and punctual attendance is essential.'
    ))

    story.append(sec(
        '7', 'Leave Entitlement',
        'As this is a training and internship program, interns are expected '
        'to maintain regular attendance throughout the internship period. '
        'Any leave must be approved in advance by the reporting manager. '
        'Excessive absenteeism or unauthorized leave may adversely affect '
        'the intern\'s performance evaluation and eligibility for Full time employment.'
    ))

    story.append(sec(
        '8', 'Notice Period &amp; Termination',
        'Either the Intern or the Company may terminate the internship by '
        'providing <b>15 days\' prior written notice</b> to the other party. '
        'In the event that the Intern discontinues the internship without '
        'serving the required notice period or obtaining prior written '
        'approval from the Company, the Intern shall be liable to pay an '
        '<b>administrative and training cost compensation of Rs. 2,000 '
        '(Indian Rupees)</b> to the Company.'
    ))

    story.append(sec(
        '9', 'Confidentiality &amp; Intellectual Property',
        'During the course of your employment and thereafter, you shall '
        'maintain strict confidentiality regarding all proprietary information, '
        'trade secrets, client data, source code, and business strategies. '
        'All work products, innovations, and intellectual property created '
        'during your employment shall remain the exclusive property of the '
        'company.'
    ))

    story.append(sec(
        '10', 'Code of Conduct',
        'You are expected to conduct yourself professionally and ethically '
        'at all times. You shall comply with all company policies, rules, '
        'and regulations as may be communicated from time to time. Any '
        'violation may result in disciplinary action.'
    ))

    story.append(sec(
        '11', 'MANDATORY DOCUMENTS – JOINING DAY CHECKLIST',
        '&#x2022; <b>Signed Offer Letter:</b> 1 copy signed on all pages.<br/>'
        '&#x2022; <b>Academic Records:</b> SSC, HSC, and Degree/Diploma '
        'certificates (Photocopy + Original for verification).<br/>'
        '&#x2022; <b>Identity Proof:</b> PAN Card and Aadhaar/Voter '
        'ID/Driving Licence (Photocopy + Original).<br/>'
        '&#x2022; <b>Photographs:</b> 1 recent passport-size color photograph.<br/>'
        '&#x2022; <b>Institutional Documents:</b> Bonafide Certificate / '
        'NOC (if applicable).'
    ))

    story.append(Spacer(1, 8))

    story.append(Paragraph(
        'We are delighted to welcome you to the '
        '<b>APARAITECH SOFTWARE COMPANY</b> family. Please sign and return '
        'the duplicate copy of this letter as your acceptance of the terms '
        'and conditions mentioned herein.',
        body
    ))

    story.append(Spacer(1, 5))

    story.append(Paragraph(
        '<b>For APARAITECH SOFTWARE COMPANY</b>', bold
    ))
    story.append(Spacer(1, 5))
    story.append(_SignatureBlock(
        _gp(base_dir, 'signature.png'),
        _gp(base_dir, 'stamp.png')
    ))

    # Candidate acceptance page
    story.append(PageBreak())
    story.append(Spacer(1, 20))
    story.append(Paragraph('ACCEPTANCE BY CANDIDATE', title))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        'I have read and understood the terms of this Business Development '
        'Associate offer, including the target-linked stipend/incentive '
        'structure, working hours, attendance and leave requirements, notice '
        'period, confidentiality obligations, code of conduct, and joining '
        'requirements. I accept this offer and agree to follow the company '
        'policies, business targets, reporting requirements, confidentiality '
        'obligations, and professional conduct standards.',
        body
    ))
    story.append(Spacer(1, 40))

    accept = Table(
        [[
            Paragraph('<b>Signature of Candidate</b>', body),
            Paragraph('<b>Date</b>', rgt)
        ]],
        colWidths=[200, 200],
        hAlign='LEFT'
    )
    accept.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (-1, -1), (-1, -1), 0)
    ]))
    story.append(accept)

    def on_page(c, doc):
        _draw_page(c, doc, base_dir)
        _draw_watermark(c, admin_user, watermark_ts, base_dir)

    frame = Frame(40, 60, W - 80, H - 165, id='main')
    template = PageTemplate(
        id='BDAOffer',
        frames=[frame],
        onPage=on_page
    )
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        pageTemplates=[template]
    )
    doc.build(story)
    buf.seek(0)

    # Existing PDF security flow retained.
    try:
        import fitz
        import pikepdf

        fitz_doc = fitz.open(
            stream=buf.read(),
            filetype='pdf'
        )
        image_pdf = io.BytesIO()
        image_canvas = rl_canvas.Canvas(
            image_pdf,
            pagesize=A4
        )
        mat = fitz.Matrix(200 / 72.0, 200 / 72.0)

        for page_num in range(len(fitz_doc)):
            page = fitz_doc.load_page(page_num)
            pix = page.get_pixmap(
                matrix=mat,
                alpha=False
            )
            image = PILImage.open(
                io.BytesIO(pix.tobytes('png'))
            )
            image_canvas.drawImage(
                ImageReader(image),
                0,
                0,
                width=W,
                height=H
            )
            image_canvas.showPage()

        image_canvas.save()
        fitz_doc.close()
        image_pdf.seek(0)

        secured = io.BytesIO()
        with pikepdf.open(image_pdf) as pdf:
            enc = pikepdf.Encryption(
                owner=owner_password,
                user='',
                allow=pikepdf.Permissions(
                    print_lowres=False,
                    print_highres=False,
                    modify_annotation=False,
                    modify_form=False,
                    modify_assembly=False,
                    modify_other=False,
                    extract=False,
                    accessibility=False,
                ),
                R=6,
            )
            pdf.save(
                secured,
                encryption=enc,
                linearize=True
            )

        secured.seek(0)
        return secured

    except ImportError:
        buf.seek(0)
        return buf
