from flask import Flask, render_template, request, send_file, session, redirect, url_for, flash, jsonify
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image, Table,
    TableStyle, BaseDocTemplate, Frame, PageTemplate, KeepTogether, PageBreak)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT, TA_LEFT
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv
import os, io, random, string, zipfile, re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None

from PIL import Image as PILImage
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader
from certificates import build_certificate_bundle, send_certificate_bundle_email
from softwaredeveloper_templates import build_software_developer_template_bundle, send_software_developer_template_email
from bda_offer import build_bda_pdf
from data_store import (DOCUMENT_TYPES, dashboard_counts, list_document_logs,
                        save_document_log, storage_backend)

load_dotenv(override=True)

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
W, H = A4

# ── Auth Config ───────────────────────────────────────────────
app.secret_key  = os.environ.get("SECRET_KEY", "development-only-change-me")
LOGIN_USER      = os.environ.get("LOGIN_UID", "admin")
LOGIN_PASS      = os.environ.get("LOGIN_PASS", "change-me-in-env")
# ── SMTP Config ──────────────────────────────────────────────
SMTP_HOST     = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER     = os.environ.get("SMTP_USER", "your@gmail.com")
SMTP_PASS     = os.environ.get("SMTP_PASS", "your_app_password")
SMTP_FROM     = os.environ.get("SMTP_FROM", SMTP_USER)
SMTP_USE_TLS  = os.environ.get("SMTP_USE_TLS", "true").strip().lower() in ("1", "true", "yes", "on")
SMTP_USE_SSL  = os.environ.get("SMTP_USE_SSL", "false").strip().lower() in ("1", "true", "yes", "on")
# ─────────────────────────────────────────────────────────────

# ── PDF SECURITY ─────────────────────────────────────────────
PDF_OWNER_PASSWORD = os.environ.get("PDF_OWNER_PASSWORD", "change-me-in-env")
PDF_USER_PASSWORD  = ""
# ─────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

DARK = colors.HexColor('#0d2b5e')
CYAN = colors.HexColor('#00aec7')
GREY = colors.HexColor('#555555')

def gp(f): return os.path.join(BASE_DIR, "static", f)

def draw_page(c, doc):
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(CYAN)
    c.rect(0, H-92, W, 4, fill=1, stroke=0)
    logo = gp("logo.png")
    if os.path.exists(logo):
        c.drawImage(logo, 14, H-80, width=80, height=60, preserveAspectRatio=True, mask='auto')
    c.setFillColor(DARK)
    c.setFont('Helvetica-Bold', 17)
    c.drawRightString(W-30, H-46, "APARAITECH SOFTWARE COMPANY")
    c.setFont('Helvetica', 9)
    c.setFillColor(CYAN)
    c.drawRightString(W-30, H-62, "We Build Your Vision")
    c.setStrokeColor(CYAN)
    c.setLineWidth(1)
    c.line(40, 52, W-40, 52)
    c.setFont('Helvetica', 7.5)
    c.setFillColor(GREY)
    c.drawCentredString(W/2, 38, "Baramati, Pune – 412306, Maharashtra  |  info@aparaitechsoftware.org  |  www.aparaitech.org")
    c.setFont('Helvetica', 8)
    c.drawRightString(W - 40, 20, f"Page {doc.page}")
    c.restoreState()

# ── LOGO WATERMARK FUNCTION ──────────────────────────────────
def draw_logo_watermark(c, admin_user, timestamp):
    """Draws logo as diagonal watermark with admin info."""
    logo_path = gp("logo.png")
    if not os.path.exists(logo_path):
        return
    
    c.saveState()
    
    # Move to center and rotate
    c.translate(W/2, H/2)
    c.rotate(30)  # 30 degree angle
    
    # Set transparency
    c.setFillAlpha(0.12)
    c.setStrokeAlpha(0.12)
    
    # Draw logo (large, centered, faded)
    logo_width = 500
    logo_height = 360
    c.drawImage(logo_path, 
                -logo_width/2, 
                -logo_height/2 + 30,
                width=logo_width, 
                height=logo_height,
                preserveAspectRatio=True, 
                mask='auto')
    
    # Admin info below logo
    c.setFont('Helvetica-Bold', 13)
    c.setFillAlpha(0.18)
    c.drawCentredString(0, -logo_height/2 - 10, f"GEN BY: {admin_user.upper()}")
    
    c.setFont('Helvetica', 9)
    c.setFillAlpha(0.15)
    c.drawCentredString(0, -logo_height/2 - 26, timestamp)
    
    # Confidential tag
    c.setFont('Helvetica-Bold', 11)
    c.setFillAlpha(0.12)
    c.drawCentredString(0, -logo_height/2 - 44, "APARAITECH CONFIDENTIAL")
    
    c.restoreState()
# ─────────────────────────────────────────────────────────────

def build_pdf(data, admin_user="ADMIN"):
    buf = io.BytesIO()
    body  = ParagraphStyle('body', fontSize=9.5, fontName='Helvetica', leading=13, textColor=colors.black, alignment=TA_JUSTIFY, spaceAfter=4)
    bold  = ParagraphStyle('bold', fontSize=9.5, fontName='Helvetica-Bold', leading=13, textColor=DARK, spaceAfter=2)
    title = ParagraphStyle('title', fontSize=13, fontName='Helvetica-Bold', textColor=DARK, alignment=TA_CENTER, spaceAfter=8)
    rgt   = ParagraphStyle('rgt', fontSize=9.5, fontName='Helvetica', textColor=colors.black, alignment=TA_RIGHT)
    digi  = ParagraphStyle('digi', fontSize=8, fontName='Courier', textColor=GREY, alignment=TA_LEFT)

    # ── CORRECTED: KeepTogether wrapper ──────────────────────
    def sec(n, head, text):
        return KeepTogether([
            Paragraph(f"<b>{n}. {head}</b>", bold),
            Paragraph(text, body),
            Spacer(1, 4)
        ])
    # ─────────────────────────────────────────────────────────

    SP = lambda n=4: Spacer(1, n)
    date_str = datetime.now().strftime('%d %B %Y')
    ref_year = datetime.now().strftime('%Y')
    ref = f"APC/HRD/{ref_year}/OFF-" + ''.join(random.choices(string.digits, k=3))
    
    # Watermark timestamp
    watermark_ts = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
    
    joining = data.get('joining_date', '')
    joining_raw = joining
    try: joining = datetime.strptime(joining, '%Y-%m-%d').strftime('%d %B %Y')
    except: pass
    end_raw = data.get('training_end_date', '')
    end_date = end_raw
    try: end_date = datetime.strptime(end_raw, '%Y-%m-%d').strftime('%d %B %Y')
    except: pass
    try:
        d1 = datetime.strptime(joining_raw, '%Y-%m-%d')
        d2 = datetime.strptime(end_raw, '%Y-%m-%d')
        months = (d2.year - d1.year) * 12 + (d2.month - d1.month)
        duration_str = f"{months:02d} Months (Fixed Term)"
    except:
        duration_str = "04 Months (Fixed Term)" 

    E = []
    top_tbl = Table([
        [Paragraph(f"<b>Ref:</b> {ref}", body), Paragraph(f"<b>Date:</b> {date_str}", rgt)]
    ], colWidths=[255, 255], hAlign='LEFT')
    top_tbl.setStyle(TableStyle([('LEFTPADDING', (0,0), (0,0), 0), ('RIGHTPADDING', (-1,-1), (-1,-1), 0)]))
    E.append(top_tbl); E.append(SP(8))
    E.append(Paragraph("OFFER OF EMPLOYMENT &amp; APPOINTMENT LETTER", title)); E.append(SP(4))
    emp_name = data.get('employee_name', 'Employee')
    E.append(Paragraph("To,", body))
    E.append(Paragraph(f"<b>Mr./Ms. {emp_name}</b>", bold))
    if data.get('college') and data.get('department'):
        E.append(Paragraph(f"{data.get('college')}, {data.get('department')}", body))
    E.append(Paragraph("Maharashtra, India", body))
    if data.get("email"):
        E.append(Paragraph(f"<b>Email:</b> {data.get('email')}", body))
    E.append(SP(6))
    position = data.get('position', 'Developer')
    E.append(Paragraph(f"<b>Subject: Offer of Employment for the position of {position}</b>", body)); E.append(SP(6))
    E.append(Paragraph(f"Dear {emp_name},", body))
    E.append(Paragraph(f"We are pleased to confirm your selection for the position of <b>{position}</b> at <b>APARAITECH SOFTWARE COMPANY</b>.", body))
    E.append(Paragraph("This letter outlines the terms and conditions of your employment with us. We are confident that your skills and experience will be a valuable addition to our team.", body)); E.append(SP(6))
    
    # ── CORRECTED: Use append() instead of extend() ──────────
    E.append(sec("1", "Position &amp; Appointment", f"You are hereby appointed as <b>{position}</b> and shall report to the designated reporting manager at our Baramati office. Your services may be transferred to any department, project, or location as per business requirements."))
    
    E.append(sec("2", "INTERNSHIP / TRAINING PERIOD", f"&#x2022; &nbsp;<b>Internship Duration:</b> {duration_str}<br/>&#x2022; &nbsp;<b>Internship Start Date:</b> {joining}<br/>&#x2022; &nbsp;<b>Internship End Date:</b> {end_date}<br/>You are required to report at our Baramati office on the training start date along with all original documents for verification."))
    
    E.append(sec("3", "Probation Period", "You will be on probation/internship for a period of Four (4) months from the date of joining. During this period, your performance will be evaluated, and upon successful completion, you will be confirmed as a regular employee based on your performance and as per company requirements. The company reserves the right to extend the probation period if deemed necessary."))
    
    stipend = data.get('stipend', '0')
    E.append(sec("4", "Compensation &amp; Benefits", f"Your internship with the organization will be for a period of 4 months. Please note that this is an unpaid internship program, and no salary, stipend, or monetary compensation shall be provided during the internship period.Upon successful completion of the internship, you will be awarded an <b>Experience Certificate</b> and relevant project documentation/completion documents. The issuance of these documents will be subject to your overall performance, attendance, discipline, project participation, and successful fulfillment of the internship requirements as evaluated by the organization."))
    
    E.append(sec("5", "Pre-Placement Offer (PPO) &amp; Full-Time Employment", "After successful completion of the Internship period, candidates may be considered for a PPO based on performance, project requirements, academic completion, and position availability. The offered package, if applicable, may range between 2.5 LPA to 4.5 LPA depending on the final evaluation. APARAITECH reserves the right to extend or decline the PPO at its sole discretion. Completion of the internship does not guarantee full-time employment. "))
    
    E.append(sec("6", "Working Hours &amp; Attendance", "The company follows a 6-day work week (9 hours/day), Monday through Saturday, 10:00 AM to 7:30 PM. You may be required to work additional hours during critical project phases. Regular and punctual attendance is essential."))
    
    E.append(sec("7", "Leave Entitlement", "As this is a training and internship program, interns are expected to maintain regular attendance throughout the internship period. Any leave must be approved in advance by the reporting manager. Excessive absenteeism or unauthorized leave may adversely affect the intern's performance evaluation and eligibility for receiving an Internship Completion Certificate, Experience Letter, and project documentation.If taking a leaves it may extend your internship"))
    
    E.append(sec("8", "Notice Period &amp; Termination", "Either the Intern or the Company may terminate the internship by providing 15 days' prior written notice to the other party.In the event that the Intern discontinues the internship without serving the required notice period or obtaining prior written approval from the Company, the Intern shall be liable to pay an administrative and training cost compensation of Rs.2,000 (Indian Rupees) to the Company.The Company reserves the right to withhold the Internship Completion Certificate, Experience Letter, project documentation, and any other internship-related benefits until all obligations under this agreement have been fulfilled."))
    
    E.append(sec("9", "Confidentiality &amp; Intellectual Property", "During the course of your employment and thereafter, you shall maintain strict confidentiality regarding all proprietary information, trade secrets, client data, source code, and business strategies. All work products, innovations, and intellectual property created during your employment shall remain the exclusive property of the company."))
    
    E.append(sec("10", "Code of Conduct", "You are expected to conduct yourself professionally and ethically at all times. You shall comply with all company policies, rules, and regulations as may be communicated from time to time. Any violation may result in disciplinary action."))
    
    # ── CORRECTED: Checklist with KeepTogether ───────────────
    docs_list = [
        "<b>Signed Offer Letter:</b> 1 copy signed on all pages.",
        "<b>Academic Records:</b> SSC, HSC, and Degree/Diploma certificates (Photocopy + Original for verification).",
        "<b>Identity Proof:</b> PAN Card and Aadhaar/Voter ID/Driving Licence (Photocopy + Original).",
        "<b>Photographs:</b> 1 recent passport-size color photograph.",
        "<b>Institutional Docs:</b> Bonafide Certificate / NOC (if applicable)."
    ]
    bul = ParagraphStyle('bul', fontSize=9, fontName='Helvetica', leading=13, leftIndent=14, textColor=colors.black, spaceAfter=2)
    
    checklist_items = [Paragraph("<b>11. MANDATORY DOCUMENTS – JOINING DAY CHECKLIST</b>", bold), Spacer(1, 2)]
    for d in docs_list:
        checklist_items.append(Paragraph(f"&#x2022;  {d}", bul))
    checklist_items.append(Spacer(1, 4))
    E.append(KeepTogether(checklist_items))
    # ─────────────────────────────────────────────────────────
    
    E.append(Paragraph("We are delighted to welcome you to the APARAITECH SOFTWARE COMPANY family. Please sign and return the duplicate copy of this letter as your acceptance of the terms and conditions mentioned here in.", body))
    E.append(Paragraph("We look forward to a long and mutually rewarding association.", body)); E.append(SP(12))
    E.append(Paragraph("<b>For APARAITECH SOFTWARE COMPANY</b>", bold)); E.append(SP(6))

    sp, st = gp("signature.png"), gp("stamp.png")
    from reportlab.platypus import Flowable
    class SignatureBlock(Flowable):
        def __init__(self, sig_path, stamp_path):
            Flowable.__init__(self)
            self.sig_path = sig_path; self.stamp_path = stamp_path
            self.width = 4*inch; self.height = 1.6*inch
        def draw(self):
            c = self.canv
            if os.path.exists(self.sig_path):
                c.drawImage(self.sig_path, 0, 0.95*inch, width=1.5*inch, height=0.6*inch, preserveAspectRatio=True, mask='auto')
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.enums import TA_LEFT
            from reportlab.platypus import Paragraph
            import datetime as dt
            now = dt.datetime.now().strftime('%d-%m-%Y %H:%M')
            style = ParagraphStyle('d', fontName='Courier', fontSize=8, textColor=colors.HexColor('#555555'), leading=12, alignment=TA_LEFT)
            lines = ["Digitally Signed by", f"Date: {now}", "<b>Managing Director</b>"]
            y = 0.6 * inch
            for line in lines:
                p = Paragraph(line, style); pw, ph = p.wrap(2.5*inch, 20); p.drawOn(c, 0, y); y -= ph + 1
            if os.path.exists(self.stamp_path):
                c.drawImage(self.stamp_path, 0.8*inch, -0.05*inch, width=1.0*inch, height=1.0*inch, preserveAspectRatio=True, mask='auto')
    E.append(SignatureBlock(sig_path=sp if os.path.exists(sp) else "", stamp_path=st if os.path.exists(st) else ""))
    E.append(PageBreak())
    E.append(SP(20)); E.append(Paragraph("ACCEPTANCE BY EMPLOYEE", title)); E.append(SP(10))
    E.append(Paragraph("I have read and understood the terms and conditions of employment as stated above. I hereby accept this offer and agree to abide by the company's policies and regulations.", body)); E.append(SP(40))
    sig_accept_tbl = Table([ [Paragraph("<b>Signature of Employee</b>", body), Paragraph("<b>Date</b>", rgt)] ], colWidths=[200, 200], hAlign='LEFT')
    sig_accept_tbl.setStyle(TableStyle([('LEFTPADDING', (0,0), (0,0), 0), ('RIGHTPADDING', (-1,-1), (-1,-1), 0)]))
    E.append(sig_accept_tbl)

    # ── STEP 1: Build PDF with logo watermark ─────────────────
    def draw_page_with_watermark(c, doc):
        draw_page(c, doc)
        draw_logo_watermark(c, admin_user, watermark_ts)
    
    frame = Frame(40, 60, W - 80, H - 165, id='main')
    pt = PageTemplate(id='Letter', frames=[frame], onPage=draw_page_with_watermark)
    doc = BaseDocTemplate(buf, pagesize=A4, pageTemplates=[pt])
    doc.build(E)
    buf.seek(0)

    # ── STEP 2: RASTERIZE ─────────────────────────────────────
    try:
        import fitz
        doc_fitz = fitz.open(stream=buf.read(), filetype="pdf")
        img_pdf_buf = io.BytesIO()
        img_canvas = rl_canvas.Canvas(img_pdf_buf, pagesize=A4)
        DPI = 200
        zoom = DPI / 72.0
        mat = fitz.Matrix(zoom, zoom)
        for page_num in range(len(doc_fitz)):
            page = doc_fitz.load_page(page_num)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_data = pix.tobytes("png")
            pil_img = PILImage.open(io.BytesIO(img_data))
            img_reader = ImageReader(pil_img)
            img_canvas.drawImage(img_reader, 0, 0, width=W, height=H)
            img_canvas.showPage()
        img_canvas.save()
        img_pdf_buf.seek(0)
        doc_fitz.close()

        # ── STEP 3: ENCRYPT ────────────────────────────────────
        import pikepdf
        src = io.BytesIO(img_pdf_buf.read())
        dst = io.BytesIO()
        with pikepdf.open(src) as pdf:
            enc = pikepdf.Encryption(
                owner=PDF_OWNER_PASSWORD,
                user=PDF_USER_PASSWORD,
                allow=pikepdf.Permissions(
                    print_lowres=False, print_highres=False, modify_annotation=False,
                    modify_form=False, modify_assembly=False, modify_other=False,
                    extract=False, accessibility=False,
                ),
                R=6
            )
            pdf.save(dst, encryption=enc, linearize=True)
        dst.seek(0)
        return dst
        
    except ImportError:
        import pikepdf
        src = io.BytesIO(buf.read())
        dst = io.BytesIO()
        with pikepdf.open(src) as pdf:
            enc = pikepdf.Encryption(
                owner=PDF_OWNER_PASSWORD,
                user=PDF_USER_PASSWORD,
                allow=pikepdf.Permissions(
                    print_lowres=False, print_highres=False, modify_annotation=False,
                    modify_form=False, modify_assembly=False, modify_other=False,
                    extract=False, accessibility=False,
                ),
                R=6
            )
            pdf.save(dst, encryption=enc)
        dst.seek(0)
        return dst

def send_offer_email(to_email, emp_name, pdf_buf, fname):
    msg = MIMEMultipart()
    msg['From'] = SMTP_FROM
    msg['To'] = to_email
    msg['Subject'] = "Offer Letter – Software Developer | Aparaitech Software Company"

    body = f"""Dear {emp_name},

Greetings from Aparaitech Software Company!

Congratulations!

We are pleased to offer you the position of *Software Developer* at Aparaitech Software Company. We are delighted to have you selected to join our organization and look forward to having you as a valuable member of our development team.

Please find your *Software Developer Offer Letter* attached to this email. The offer letter contains important information regarding your position, joining details, compensation, terms and conditions, responsibilities, and other employment-related information.

Kindly go through the offer letter carefully. If you accept the terms and conditions mentioned in the offer letter, please:

1. Sign the offer letter.
2. Keep a copy for your records.
3. Send the signed copy back to the HR Department by replying to this email.

Your signed offer letter will be considered as confirmation of your acceptance of the offer.

As a Software Developer, you will have the opportunity to work on real-world software projects, collaborate with the development team, enhance your technical skills, and contribute to the company's products and solutions.

We encourage you to maintain professionalism, continuously develop your technical skills, and actively participate in team activities and assigned projects.

If you have any questions or require clarification regarding the offer letter or joining process, please feel free to contact the HR Department.

Once again, congratulations on your selection!

We are excited to welcome you to *Aparaitech Software Company* and look forward to a successful and productive association with you.

Warm regards,

HR Department
Aparaitech Software Company
Baramati, Pune – 413102
info@ai.aparaitech.org
www.aparaitech.org
"""

    msg.attach(MIMEText(body, 'plain'))

    part = MIMEBase('application', 'octet-stream')
    part.set_payload(pdf_buf.read())
    encoders.encode_base64(part)
    part.add_header(
        'Content-Disposition',
        f'attachment; filename="{fname}"'
    )
    msg.attach(part)

    server = None
    try:
        if SMTP_USE_SSL or SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
            server.ehlo()
            if SMTP_USE_TLS:
                server.starttls()
                server.ehlo()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, to_email, msg.as_string())
    finally:
        if server is not None:
            try:
                if getattr(server, "sock", None) is not None:
                    server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass
def send_bda_offer_email(to_email, candidate_name, pdf_buf, fname):
    msg = MIMEMultipart()
    msg['From'] = SMTP_FROM
    msg['To'] = to_email
    msg['Subject'] = 'Business Development Associate Offer Letter | Aparaitech Software'

    body = f"""Dear {candidate_name},

Greetings from Aparaitech Software Company.

We are pleased to offer you the position of Business Development Associate (BDA).

Your role follows a target-linked performance model. The stipend / incentive is based on verified target achievement, conversion quality, consistency, attendance, reporting discipline, and management evaluation.

Stipend: Up to INR 15,000 per month, based on achievement of applicable targets and performance as per the company incentive policy.

Upon successfully completing the training period and meeting the required performance standards, you may be considered for a full-time employment opportunity with the company. The full-time position may offer a CTC of up to INR 4.5 LPA to INR 5 LPA, subject to performance, eligibility, role requirements, management evaluation, and company policies.

Please find your BDA Offer Letter attached. Kindly check the offer letter carefully, sign it, and revert back to this email with the signed copy as soon as possible.

We look forward to your contribution to the growth of Aparaitech Software.

Warm regards,
HR Department
Aparaitech Software Company
Hinjewadi, Pune - 411057
info@ai.aparaitech.org | www.aparaitech.org
"""

    msg.attach(MIMEText(body, 'plain'))

    part = MIMEBase('application', 'octet-stream')
    pdf_buf.seek(0)
    part.set_payload(pdf_buf.read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="{fname}"')
    msg.attach(part)

    server = None
    try:
        if SMTP_USE_SSL or SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
            server.ehlo()
            if SMTP_USE_TLS:
                server.starttls()
                server.ehlo()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, to_email, msg.as_string())
    finally:
        if server is not None:
            try:
                if getattr(server, "sock", None) is not None:
                    server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass



def smtp_config():
    return {
        "host": SMTP_HOST,
        "port": SMTP_PORT,
        "username": SMTP_USER,
        "password": SMTP_PASS,
        "sender": SMTP_FROM,
        "use_tls": SMTP_USE_TLS,
        "use_ssl": SMTP_USE_SSL,
    }


def certificate_zip(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for _, (filename, content) in files.items():
            archive.writestr(filename, content)
    out.seek(0)
    return out


def certificate_form_payload(source):
    keys = [
        "candidate_name", "email", "domain", "duration_months", "start_date",
        "end_date", "issue_date", "progress_percent", "mode", "credential_id",
        "verification_url",
    ]
    return {key: source.get(key, "") for key in keys}

def log_generated_document(document_type, data, *, email_status, email_error, filename, extra=None):
    try:
        save_document_log(
            document_type, data, admin_user=session.get("admin_user", "ADMIN"),
            email_status=email_status, email_error=email_error, filename=filename, extra=extra
        )
    except Exception:
        # Audit logging must never break the existing PDF/ZIP generation flow.
        app.logger.exception("Document audit logging failed")


def _xlsx_safe_sheet_name(name):
    name = re.sub(r"[\[\]:*?/\\]", " ", str(name or "Data")).strip() or "Data"
    return name[:31]


def build_logs_xlsx(records, requested_type=None):
    if xlsxwriter is None:
        raise RuntimeError("Excel export dependency is not installed. Run: pip install -r requirements.txt")
    out = io.BytesIO()
    workbook = xlsxwriter.Workbook(out, {"in_memory": True})
    header = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#0D2B5E", "border": 1, "align": "center", "valign": "vcenter"})
    cell = workbook.add_format({"border": 1, "valign": "top"})
    wrap = workbook.add_format({"border": 1, "valign": "top", "text_wrap": True})
    date_fmt = workbook.add_format({"border": 1, "valign": "top", "num_format": "yyyy-mm-dd hh:mm"})

    groups = {}
    for record in records:
        groups.setdefault(record.get("document_type") or "other", []).append(record)
    if requested_type == "all":
        for dtype in DOCUMENT_TYPES:
            groups.setdefault(dtype, [])
    elif requested_type and requested_type not in groups:
        groups[requested_type] = []
    if not groups:
        groups[requested_type or "all_records"] = []

    base_cols = [
        ("created_at", "Generated At"), ("name", "Name"), ("email", "Email"),
        ("email_status", "Email Status"), ("admin_user", "Generated By"),
        ("filename", "Downloaded File"), ("email_error", "Email Error"),
    ]
    for dtype, rows in groups.items():
        dynamic_keys = []
        seen = set()
        for record in rows:
            for key in (record.get("data") or {}).keys():
                if key not in seen and key not in {"name", "email"}:
                    seen.add(key); dynamic_keys.append(key)
        dynamic_keys.sort()
        columns = base_cols + [(f"data.{k}", k.replace("_", " ").title()) for k in dynamic_keys]
        sheet = workbook.add_worksheet(_xlsx_safe_sheet_name(DOCUMENT_TYPES.get(dtype, dtype.replace("_", " ").title())))
        sheet.freeze_panes(1, 0)
        sheet.autofilter(0, 0, max(0, len(rows)), max(0, len(columns)-1))
        sheet.set_row(0, 26)
        for col, (_, title) in enumerate(columns):
            sheet.write(0, col, title, header)
            sheet.set_column(col, col, 18 if col != 1 else 24)
        if len(columns) > 6:
            sheet.set_column(6, 6, 30)
        for r_idx, record in enumerate(rows, start=1):
            for c_idx, (key, _) in enumerate(columns):
                if key.startswith("data."):
                    value = (record.get("data") or {}).get(key[5:], "")
                else:
                    value = record.get(key, "")
                fmt = wrap if c_idx in (5, 6) or len(str(value)) > 35 else cell
                if key == "created_at" and value:
                    try:
                        parsed = datetime.fromisoformat(str(value))
                        sheet.write_datetime(r_idx, c_idx, parsed.replace(tzinfo=None), date_fmt)
                        continue
                    except Exception:
                        pass
                sheet.write(r_idx, c_idx, value, fmt)
    workbook.close()
    out.seek(0)
    return out


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        uid = request.form.get("uid", "").strip()
        pwd = request.form.get("password", "").strip()
        if uid == LOGIN_USER and pwd == LOGIN_PASS:
            session['logged_in'] = True
            session['admin_user'] = uid
            return redirect(url_for('home'))
        else:
            error = "Invalid username or password."
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/")
@login_required
def home():
    counts = dashboard_counts()
    recent_logs = list_document_logs(limit=12)
    return render_template(
        "index.html", admin_user=session.get("admin_user", "ADMIN"), counts=counts,
        recent_logs=recent_logs, document_types=DOCUMENT_TYPES, storage_backend=storage_backend()
    )

@app.route("/admin/data")
@login_required
def admin_data():
    dtype = request.args.get("type", "all").strip()
    if dtype != "all" and dtype not in DOCUMENT_TYPES:
        dtype = "all"
    records = list_document_logs(None if dtype == "all" else dtype, limit=1000)
    return render_template(
        "admin_data.html", admin_user=session.get("admin_user", "ADMIN"), records=records,
        active_type=dtype, document_types=DOCUMENT_TYPES, counts=dashboard_counts(),
        storage_backend=storage_backend()
    )


@app.route("/admin/data/export")
@login_required
def export_admin_data():
    dtype = request.args.get("type", "all").strip()
    if dtype != "all" and dtype not in DOCUMENT_TYPES:
        dtype = "all"
    records = list_document_logs(None if dtype == "all" else dtype, limit=5000)
    try:
        workbook = build_logs_xlsx(records, dtype)
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    label = "All_Document_Data" if dtype == "all" else DOCUMENT_TYPES[dtype].replace(" ", "_")
    filename = f"Aparaitech_{label}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(
        workbook, as_attachment=True, download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.route("/employment")
@login_required
def employment_form():
    """Show Employment offer letter form."""
    return render_template("employment.html", admin_user=session.get('admin_user', 'ADMIN'))

@app.route("/generate", methods=["POST"])
@login_required
def generate():
    keys = ["employee_name", "email", "college", "department", "position", "joining_date", "training_end_date", "stipend"]
    data = {k: request.form.get(k, '') for k in keys}
    
    # Get admin who generated this offer
    admin_user = session.get('admin_user', 'ADMIN')
    
    buf = build_pdf(data, admin_user=admin_user)
    fname = f"{data['employee_name'].replace(' ','_')}_Aparaitech_Offer.pdf"
    email_status = "sent"; email_error = ""
    if data.get('email'):
        try:
            buf.seek(0)
            send_offer_email(data['email'], data['employee_name'], buf, fname)
        except Exception as e:
            email_status = "failed"; email_error = str(e)
    log_generated_document("employment_offer", data, email_status=email_status, email_error=email_error, filename=fname)
    buf.seek(0)
    response = send_file(buf, as_attachment=True, download_name=fname, mimetype="application/pdf")
    response.headers['X-Email-Status'] = email_status
    response.headers['X-Email-Error'] = email_error
    response.headers['X-Filename'] = fname
    response.headers['Access-Control-Expose-Headers'] = 'X-Email-Status, X-Email-Error, X-Filename'
    return response


@app.route("/bda-employment")
@login_required
def bda_employment_form():
    """Show Business Development Associate offer-letter form."""
    return render_template("bda_employment.html", admin_user=session.get('admin_user', 'ADMIN'))


@app.route("/generate-bda", methods=["POST"])
@login_required
def generate_bda():
    """Generate a dedicated target-based BDA offer letter PDF."""
    keys = [
        "employee_name", "email", "college", "department", "joining_date",
        "training_end_date", "monthly_target", "reporting_to", "work_mode",
    ]
    data = {k: request.form.get(k, '') for k in keys}
    admin_user = session.get('admin_user', 'ADMIN')

    buf = build_bda_pdf(
        data,
        base_dir=BASE_DIR,
        admin_user=admin_user,
        owner_password=PDF_OWNER_PASSWORD,
    )
    safe_name = re.sub(r'[^A-Za-z0-9_-]+', '_', data.get('employee_name') or 'Candidate').strip('_')
    fname = f"{safe_name}_Aparaitech_BDA_Offer.pdf"

    email_status = "sent"
    email_error = ""
    if data.get('email'):
        try:
            buf.seek(0)
            send_bda_offer_email(data['email'], data['employee_name'], buf, fname)
        except Exception as exc:
            email_status = "failed"
            email_error = str(exc)

    log_generated_document("bda_offer", data, email_status=email_status, email_error=email_error, filename=fname)
    buf.seek(0)
    response = send_file(buf, as_attachment=True, download_name=fname, mimetype="application/pdf")
    response.headers['X-Email-Status'] = email_status
    response.headers['X-Email-Error'] = email_error
    response.headers['X-Filename'] = fname
    response.headers['Access-Control-Expose-Headers'] = 'X-Email-Status, X-Email-Error, X-Filename'
    return response

    # ── LIVE PROJECT ROUTES ──────────────────────────────────────

@app.route("/live-project")
@login_required
def live_project_form():
    """Show Live Project offer letter form."""
    return render_template("live_project.html", admin_user=session.get('admin_user', 'ADMIN'))

@app.route("/generate-live-project", methods=["POST"])
@login_required
def generate_live_project():
    """Generate Live Project offer letter PDF."""
    from live_project import build_live_project_pdf, send_live_project_email
    
    keys = ["candidate_name", "email", "college", "department", "domain", 
            "start_date", "end_date", "location", "stipend"]
    data = {k: request.form.get(k, '') for k in keys}
    
    admin_user = session.get('admin_user', 'ADMIN')
    
    buf = build_live_project_pdf(data, admin_user=admin_user)
    fname = f"{data['candidate_name'].replace(' ','_')}_LiveProject_Offer.pdf"
    
    # Email
    email_status = "sent"
    email_error = ""
    if data.get('email'):
        try:
            buf.seek(0)
            smtp_config = {
                'host': SMTP_HOST,
                'port': SMTP_PORT,
                'user': SMTP_USER,
                'pass': SMTP_PASS,
                'from': SMTP_FROM,
                'use_tls': SMTP_USE_TLS,
                'use_ssl': SMTP_USE_SSL
            }
            send_live_project_email(data['email'], data['candidate_name'], buf, fname, smtp_config)
        except Exception as e:
            email_status = "failed"
            email_error = str(e)
    
    log_generated_document("live_project_offer", data, email_status=email_status, email_error=email_error, filename=fname)
    buf.seek(0)
    response = send_file(buf, as_attachment=True, download_name=fname, mimetype="application/pdf")
    response.headers['X-Email-Status'] = email_status
    response.headers['X-Email-Error'] = email_error
    response.headers['X-Filename'] = fname
    response.headers['Access-Control-Expose-Headers'] = 'X-Email-Status, X-Email-Error, X-Filename'
    return response


@app.route("/certificates")
@login_required
def certificate_form():
    """Show the single form that generates all three certificate PDFs."""
    return render_template("certificates.html", admin_user=session.get("admin_user", "ADMIN"))


@app.route("/software-developer-templates")
@login_required
def software_developer_templates_form():
    return render_template("softwaredeveloper_templates.html", admin_user=session.get("admin_user", "ADMIN"))


@app.route("/generate-software-developer-templates", methods=["POST"])
@login_required
def generate_software_developer_templates():
    try:
        data, files = build_software_developer_template_bundle(request.form, BASE_DIR)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    email_status = "skipped"
    email_error = ""
    if data.get("email"):
        try:
            send_software_developer_template_email(
                data["email"], data["candidate_name"], files, smtp_config()
            )
            email_status = "sent"
        except Exception as exc:
            email_status = "failed"
            email_error = re.sub(r"[\r\n]+", " ", str(exc))[:500]

    bundle = certificate_zip(files)
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", data["candidate_name"]).strip("_") or "Candidate"
    filename = f"{safe_name}_Software_Developer_Internship_Documents.zip"
    log_generated_document("software_developer", data, email_status=email_status, email_error=email_error, filename=filename, extra={"credential_id": data.get("credential_id", "")})
    response = send_file(bundle, as_attachment=True, download_name=filename, mimetype="application/zip")
    response.headers["X-Email-Status"] = email_status
    response.headers["X-Email-Error"] = email_error
    response.headers["X-Credential-ID"] = data["credential_id"]
    response.headers["X-Filename"] = filename
    response.headers["Access-Control-Expose-Headers"] = "X-Email-Status, X-Email-Error, X-Credential-ID, X-Filename"
    return response


@app.route("/generate-certificates", methods=["POST"])
@login_required
def generate_certificates():
    """Generate, email, and download all three certificates as one ZIP."""
    try:
        data, files = build_certificate_bundle(certificate_form_payload(request.form), BASE_DIR)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    email_status = "sent"
    email_error = ""
    try:
        send_certificate_bundle_email(
    data.get('email') or request.form.get('email'),
    data.get('candidate_name') or data.get('name') or request.form.get('candidate_name') or request.form.get('name'),
    files,
    smtp_config(),
    domain=data.get('domain') or request.form.get('domain') or 'Live Project'
)
    except Exception as exc:
        email_status = "failed"
        email_error = re.sub(r"[\r\n]+", " ", str(exc))[:500]

    bundle = certificate_zip(files)
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", data["candidate_name"]).strip("_") or "Candidate"
    filename = f"{safe_name}_Aparaitech_Certificates.zip"
    log_generated_document("certificates", data, email_status=email_status, email_error=email_error, filename=filename, extra={"credential_id": data.get("credential_id", "")})
    response = send_file(bundle, as_attachment=True, download_name=filename, mimetype="application/zip")
    response.headers["X-Email-Status"] = email_status
    response.headers["X-Email-Error"] = email_error
    response.headers["X-Credential-ID"] = data["credential_id"]
    response.headers["X-Filename"] = filename
    response.headers["Access-Control-Expose-Headers"] = (
        "X-Email-Status, X-Email-Error, X-Credential-ID, X-Filename"
    )
    return response


if __name__ == "__main__":
    app.run(debug=True)
