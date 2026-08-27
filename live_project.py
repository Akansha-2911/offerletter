from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image, Table,
    TableStyle, BaseDocTemplate, Frame, PageTemplate, KeepTogether, PageBreak)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT, TA_LEFT
from datetime import datetime
import os, io, random, string
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from PIL import Image as PILImage
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader

# ── PDF SECURITY ─────────────────────────────────────────────
PDF_OWNER_PASSWORD = os.environ.get("PDF_OWNER_PASSWORD", "change-me-in-env")
PDF_USER_PASSWORD  = ""
# ─────────────────────────────────────────────────────────────

DARK = colors.HexColor('#0d2b5e')
CYAN = colors.HexColor('#00aec7')
GREY = colors.HexColor('#555555')

def gp(base_dir, f): 
    return os.path.join(base_dir, "static", f)

def draw_page_live(c, doc, base_dir):
    """Header/footer for Live Project Offer Letter."""
    W, H = A4
    c.saveState()
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Cyan accent stripe
    c.setFillColor(CYAN)
    c.rect(0, H-85, W, 4, fill=1, stroke=0)

    # Logo
    logo = gp(base_dir, "logo.png")
    if os.path.exists(logo):
        c.drawImage(logo, 30, H-75, width=70, height=50, preserveAspectRatio=True, mask='auto')

    # Company name
    c.setFillColor(DARK)
    c.setFont('Helvetica-Bold', 16)
    c.drawRightString(W-30, H-50, "APARAITECH SOFTWARE COMPANY")
    c.setFont('Helvetica', 8)
    c.setFillColor(GREY)
    c.drawRightString(W-30, H-64, "Live Project Program | Baramati, Pune – 412306")

    # Footer line
    c.setStrokeColor(CYAN)
    c.setLineWidth(0.8)
    c.line(40, 55, W-40, 55)

    c.setFont('Helvetica', 7)
    c.setFillColor(GREY)
    c.drawCentredString(W/2, 42, "info@aparaitechsoftware.org | www.aparaitech.org | +91-9110406075")
    c.setFont('Helvetica', 8)
    c.drawRightString(W - 40, 25, f"Page {doc.page}")
    c.restoreState()

def draw_logo_watermark_live(c, admin_user, timestamp):
    """Watermark for Live Project PDF."""
    W, H = A4
    logo_path = gp(os.path.dirname(os.path.abspath(__file__)), "logo.png")
    if not os.path.exists(logo_path):
        return

    c.saveState()
    c.translate(W/2, H/2)
    c.rotate(25)
    c.setFillAlpha(0.10)
    c.setStrokeAlpha(0.10)

    logo_width = 450
    logo_height = 320
    c.drawImage(logo_path, -logo_width/2, -logo_height/2 + 20,
                width=logo_width, height=logo_height,
                preserveAspectRatio=True, mask='auto')

    c.setFont('Helvetica-Bold', 12)
    c.setFillAlpha(0.15)
    c.drawCentredString(0, -logo_height/2 - 15, f"GEN BY: {admin_user.upper()} | {timestamp}")
    c.setFont('Helvetica-Bold', 10)
    c.setFillAlpha(0.12)
    c.drawCentredString(0, -logo_height/2 - 32, "LIVE PROJECT - CONFIDENTIAL")

    c.restoreState()

def build_live_project_pdf(data, admin_user="ADMIN"):
    """Build 3-Month Live Project Offer Letter PDF."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    W, H = A4
    buf = io.BytesIO()

    body = ParagraphStyle('body', fontSize=10, fontName='Helvetica', leading=14, 
                          textColor=colors.black, alignment=TA_JUSTIFY, spaceAfter=6)
    bold = ParagraphStyle('bold', fontSize=10, fontName='Helvetica-Bold', leading=14, 
                          textColor=DARK, spaceAfter=4)
    title = ParagraphStyle('title', fontSize=16, fontName='Helvetica-Bold', 
                           textColor=DARK, alignment=TA_CENTER, spaceAfter=12)
    heading = ParagraphStyle('heading', fontSize=12, fontName='Helvetica-Bold', 
                             textColor=DARK, spaceAfter=6, spaceBefore=10)
    rgt = ParagraphStyle('rgt', fontSize=10, fontName='Helvetica', 
                         textColor=colors.black, alignment=TA_RIGHT)

    SP = lambda n=6: Spacer(1, n)

    date_str = datetime.now().strftime('%d %B %Y')
    ref_year = datetime.now().strftime('%Y')
    ref = f"APC/LPP/{ref_year}/" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

    watermark_ts = datetime.now().strftime('%d-%m-%Y %H:%M:%S')

    # Format dates
    start_date = data.get('start_date', '')
    try: start_date_fmt = datetime.strptime(start_date, '%Y-%m-%d').strftime('%d %B %Y')
    except: start_date_fmt = start_date

    end_date = data.get('end_date', '')
    try: end_date_fmt = datetime.strptime(end_date, '%Y-%m-%d').strftime('%d %B %Y')
    except: end_date_fmt = end_date

    E = []

    # Reference & Date
    top_tbl = Table([
        [Paragraph(f"<b>Ref No:</b> {ref}", body),
         Paragraph(f"<b>Date:</b> {date_str}", rgt)]
    ], colWidths=[255, 255], hAlign='LEFT')
    top_tbl.setStyle(TableStyle([
        ('LEFTPADDING', (0,0), (0,0), 0),
        ('RIGHTPADDING', (-1,-1), (-1,-1), 0),
    ]))
    E.append(top_tbl); E.append(SP(10))

    # Title
    E.append(Paragraph("LIVE PROJECT PROGRAM", title))
    E.append(Paragraph("<b>OFFER LETTER</b>", title))
    E.append(SP(8))

    # To Section
    E.append(Paragraph("To,", body))
    E.append(Paragraph(f"<b>{data.get('candidate_name', 'Candidate')}</b>", bold))
    if data.get('college'):
        E.append(Paragraph(f"{data.get('college')}", body))
    if data.get('department'):
        E.append(Paragraph(f"Department: {data.get('department')}", body))
    E.append(Paragraph("Maharashtra, India", body))
    if data.get('email'):
        E.append(Paragraph(f"<b>Email:</b> {data.get('email')}", body))
    E.append(SP(8))

    # Subject
    domain = data.get('domain', 'Web Development')
    E.append(Paragraph(f"<b>Subject: Offer for 3-Month Live Project Program in {domain}</b>", body))
    E.append(SP(8))

    # Salutation
    E.append(Paragraph(f"Dear {data.get('candidate_name', 'Candidate')},", body))
    E.append(Paragraph(
        f"We are pleased to offer you an opportunity to participate in the <b>Live Project Program</b> in "
        f"<b>{domain}</b> at <b>APARAITECH SOFTWARE COMPANY</b>. This program is designed to help you "
        f"enhance your technical knowledge, work on real-world projects, and gain practical industry experience.",
        body))
    E.append(SP(6))

    # Program Details Section
    E.append(Paragraph("<b>1. PROGRAM DETAILS</b>", heading))
    E.append(Paragraph(
        f"&#x2022; <b>Domain:</b> {domain}<br/>"
        f"&#x2022; <b>Duration:</b> 3 Months (Fixed Term)<br/>"
        f"&#x2022; <b>Project Start Date:</b> {start_date_fmt}<br/>"
        f"&#x2022; <b>Project End Date:</b> {end_date_fmt}<br/>"
        f"&#x2022; <b>Location:</b> {data.get('location', 'Online Mode')}<br/>"
        f"&#x2022; <b>Program Type:</b> Live Project / Internship<br/>",
        body))
    E.append(SP(4))

    # About Program
    E.append(Paragraph("<b>2. ABOUT THE PROGRAM</b>", heading))
    E.append(Paragraph(
        "Our team is pleased to welcome you to the Live Project Program at Aparaitech Software. "
        "During this program, you will work on industry-oriented projects and gain practical, real-world "
        "development experience under the guidance of senior developers and project managers.",
        body))
    E.append(Paragraph(
        "We believe this opportunity will help you enhance your technical skills and build strong "
        "practical knowledge in the field of " + domain + ".",
        body))
    E.append(SP(4))

    # Compensation
    E.append(Paragraph("<b>3. COMPENSATION & BENEFITS</b>", heading))
    E.append(Paragraph(
        "As a participant in this program, you will not be considered an employee of the company. "
        "This program is designed to provide practical learning experience, industry exposure, and skill development.",
        body))
    E.append(Paragraph(
        "<b>Stipend:</b> You will receive compensation based on your performance during the internship. "
        "The stipend amount, if applicable, will be communicated separately by the HR department.",
        body))
    E.append(Paragraph(
        "<b>Note:</b> Participation in this internship program does not guarantee employment with the company. "
        "If an employment opportunity is offered in the future, the terms and conditions of employment, "
        "including compensation and benefits, will be communicated separately and will follow company policies.",
        body))
    E.append(SP(4))

    # Evaluation
    E.append(Paragraph("<b>4. PERFORMANCE EVALUATION</b>", heading))
    E.append(Paragraph(
        "Upon successful completion of at least <b>95%</b> of the assigned project works and based on "
        "satisfactory performance, you will be eligible to appear for the <b>HR Evaluation Round</b>.",
        body))
    E.append(Paragraph(
        "A total of <b>3 reviews</b> will be conducted during the training period:<br/>"
        "&#x2022; Each review will be conducted at the end of every month<br/>"
        "&#x2022; All 3 reviews are mandatory to complete<br/>"
        "&#x2022; After completion of all reviews, trainees must submit their final project<br/>"
        "&#x2022; Project submission is mandatory for certificate issuance<br/>"
        "&#x2022; Failure to submit the project will result in non-release of the Project Completion Certificate",
        body))
    E.append(SP(4))

    # Rules & Regulations
    E.append(Paragraph("<b>5. RULES & REGULATIONS</b>", heading))
    rules = [
        "The trainee must follow all company rules, policies, and disciplinary guidelines during the entire training period.",
        "English communication must be maintained during all official meetings, discussions, and communications.",
        "Professional behaviour and discipline must be maintained at all times during sessions.",
        "<b>Login Time:</b> Trainees must log in between 9:30 AM to 10:30 AM. <b>Logout Time:</b> Trainees must log out between 6:30 PM to 7:30 PM. Adherence to these timings is strictly mandatory.",
        "Daily Attendance is compulsory. Attendance must be marked through the assigned system/platform every working day.",
        "Daily Work Report Sheet submission is mandatory. Trainees must fill and submit their work report daily without fail.",
        "Weekly off will be provided as per company policy.",
        "In case of any emergency or inability to attend, trainees must inform both the HR department and Team Leader in advance or at the earliest possible time.",
        "Confidentiality of company data, project details, and internal communication must be strictly maintained during and after the training period."
    ]
    for i, rule in enumerate(rules, 1):
        E.append(Paragraph(f"{i}. {rule}", body))
    E.append(SP(4))

    # Confidentiality
    E.append(Paragraph("<b>6. CONFIDENTIALITY AGREEMENT</b>", heading))
    E.append(Paragraph(
        "During the internship, you may have access to confidential, proprietary, or trade secret information "
        "belonging to the company. You must keep all such information strictly confidential. "
        "You are not allowed to use company information for personal gain. "
        "You must not disclose confidential information to anyone outside the organization.",
        body))
    E.append(SP(4))

    # Company Policies
    E.append(Paragraph("<b>7. COMPANY POLICIES</b>", heading))
    E.append(Paragraph(
        "<b>Professional Conduct:</b> Participants are expected to maintain professional behavior, "
        "respect team members, and follow ethical work practices during the program.",
        body))
    E.append(Paragraph(
        "<b>Anti-Harassment Policy:</b> The company maintains a zero-tolerance policy for harassment "
        "or discrimination based on gender, religion, race, nationality, or any other personal characteristic. "
        "Any inappropriate behavior may lead to immediate removal from the program.",
        body))
    E.append(Paragraph(
        "<b>Agreement Terms:</b> This letter constitutes the complete understanding between you and the "
        "company regarding your internship and supersedes all prior discussions or agreements. "
        "Any revisions to this letter must be made in writing and signed by both parties.",
        body))
    E.append(SP(4))

    # Termination
    E.append(Paragraph("<b>8. TERMINATION</b>", heading))
    E.append(Paragraph(
        "The Company reserves the right to withhold the Internship Completion Certificate, Experience Letter, "
        "project documentation, and any other internship-related benefits until all obligations under this agreement have been fulfilled.",
        body))
    E.append(SP(4))

    # Closing
    E.append(Paragraph(
        "We hope that your internship with the company will be successful and rewarding. "
        "Please indicate your acceptance of this offer by signing below and returning it to our company.",
        body))
    E.append(SP(8))

    # Terms and Conditions Note in PDF
    E.append(Paragraph(
        "<b>IMPORTANT:</b> Before signing this offer letter, kindly go through the terms and conditions "
        "of Aparaitech Software at <b>https://terms.aparaitech.org</b>. By signing this offer letter, you "
        "acknowledge that you have read, understood, and agree to abide by all the terms and conditions stated therein.",
        ParagraphStyle('terms', fontName='Helvetica-Bold', fontSize=9, textColor=DARK, 
                       leading=14, backColor=colors.HexColor('#fff3e0'), 
                       borderColor=colors.HexColor('#ff9800'), borderWidth=1,
                       borderPadding=8, spaceAfter=6)
    ))
    E.append(SP(8))

        # ============================================
    # SIGNATURE & STAMP SECTION - LEFT ALIGNED
    # ============================================
    E.append(Paragraph("We look forward to a long and mutually rewarding association.", body))
    E.append(SP(12))

    E.append(Paragraph("<b>For APARAITECH SOFTWARE COMPANY</b>", bold))
    E.append(SP(6))

    sp = gp(base_dir, "signature.png")
    st = gp(base_dir, "stamp.png")

    digi = ParagraphStyle(
    'digi',
    fontName='Courier',
    fontSize=8,
    textColor=GREY,
    leading=10
    )

    from reportlab.platypus import Flowable

    class SignatureBlock(Flowable):
        def __init__(self, sig_path, stamp_path):
            Flowable.__init__(self)
            self.sig_path = sig_path
            self.stamp_path = stamp_path
            self.width = 4 * inch
            self.height = 1.6 * inch

        def draw(self):
            c = self.canv

            # Signature
            if os.path.exists(self.sig_path):
                c.drawImage(
                    self.sig_path,
                    0,
                    0.95 * inch,
                    width=1.5 * inch,
                    height=0.6 * inch,
                    preserveAspectRatio=True,
                    mask='auto'
                )

            now = datetime.now().strftime('%d-%m-%Y %H:%M')

            lines = [
                "Digitally Signed by",
                f"Date: {now}",
                "<b>Managing Director</b>"
            ]

            y = 0.6 * inch

            for line in lines:
                p = Paragraph(line, digi)
                pw, ph = p.wrap(2.5 * inch, 20)
                p.drawOn(c, 0, y)
                y -= ph + 1

            # Stamp
            if os.path.exists(self.stamp_path):
                c.drawImage(
                    self.stamp_path,
                    0.8 * inch,
                    -0.05 * inch,
                    width=1.0 * inch,
                    height=1.0 * inch,
                    preserveAspectRatio=True,
                    mask='auto'
                )

    E.append(
        SignatureBlock(
            sig_path=sp if os.path.exists(sp) else "",
            stamp_path=st if os.path.exists(st) else ""
        )
    )

   

    # Revert instructions
    E.append(SP(12))
    E.append(Paragraph(
        "<b>IMPORTANT:</b> Please sign this offer letter on the acceptance page (Page 2), scan it, "
        "and revert back to <b>hr.aparaitech@gmail.com</b> within <b>3 business days</b> to confirm your acceptance.",
        ParagraphStyle('revert', fontName='Helvetica-Bold', fontSize=9, textColor=DARK, 
                       leading=14, backColor=colors.HexColor('#fff8e1'), 
                       borderColor=colors.HexColor('#ffc107'), borderWidth=1,
                       borderPadding=8, spaceAfter=6)
    ))
    E.append(SP(8))

    # Page Break for Acceptance
    E.append(PageBreak())
    E.append(SP(20))
    E.append(Paragraph("OFFER ACCEPTANCE", title))
    E.append(SP(10))
    E.append(Paragraph(
        "I have read and understood the terms and conditions, and I accept this offer, as set forth above, "
        "with APARAITECH SOFTWARE COMPANY.",
        body))
    E.append(SP(8))

    # Candidate Details
    E.append(Paragraph("<b>Candidate Details:</b>", bold))
    E.append(Paragraph(f"Name: {data.get('candidate_name', '_____________________')}", body))
    E.append(Paragraph(f"College: {data.get('college', '_____________________')}", body))
    E.append(Paragraph(f"Department: {data.get('department', '_____________________')}", body))
    E.append(SP(20))

    # Signature lines
    E.append(Paragraph("Please sign below and date:", body))
    E.append(SP(16))

    sig_tbl = Table([
        [Paragraph("<b>Candidate's Signature</b>", body), 
         Paragraph("<b>Date</b>", rgt)],
        [Paragraph("___________________________", body), 
         Paragraph("___________________________", rgt)]
    ], colWidths=[255, 255], hAlign='LEFT')
    sig_tbl.setStyle(TableStyle([
        ('LEFTPADDING', (0,0), (0,0), 0),
        ('RIGHTPADDING', (-1,-1), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,0), 40),
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
    ]))
    E.append(sig_tbl)

    E.append(SP(16))
    E.append(Paragraph(
        "<b> Revert Instructions:</b> After signing, please scan this page and email it to "
        "<b>hr@aparaitechsoftware.org</b> with subject line: "
        f"<i>\"Offer Acceptance - {data.get('candidate_name', 'Candidate')} - Live Project\"</i>",
        ParagraphStyle('revert2', fontName='Helvetica', fontSize=9, textColor=GREY, leading=14)
    ))

    # Build PDF
    def draw_page_with_watermark(c, doc):
        draw_page_live(c, doc, base_dir)
        draw_logo_watermark_live(c, admin_user, watermark_ts)

    frame = Frame(40, 60, W - 80, H - 160, id='main')
    pt = PageTemplate(id='LiveProject', frames=[frame], onPage=draw_page_with_watermark)
    doc = BaseDocTemplate(buf, pagesize=A4, pageTemplates=[pt])
    doc.build(E)
    buf.seek(0)

    # Rasterize & Encrypt
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

def send_live_project_email(to_email, candidate_name, pdf_buf, fname, smtp_config):
    """Send Live Project offer email with revert instructions."""
    msg = MIMEMultipart()
    msg['From'] = smtp_config['from']
    msg['To'] = to_email
    msg['Subject'] = f"Live Project Program Offer Letter – Aparaitech Software"

    body = f"""Dear {candidate_name},

Congratulations! You have been selected for the 3-Month Live Project Program at Aparaitech Software Company.

Please find your offer letter attached to this email. 

📋 NEXT STEPS:
1. Download and print the attached PDF
2. Review all terms and conditions carefully
3. Sign the "OFFER ACCEPTANCE" page (Page 2)
4. Scan the signed acceptance page
5. Email the scanned copy to: hr@aparaitechsoftware.org
6. Subject line: "Offer Acceptance - {candidate_name} - Live Project"
7. Complete within 3 business days

IMPORTANT NOTE:
Before signing this offer letter, kindly go through the terms and conditions of Aparaitech Software at https://terms.aparaitech.org. By signing this offer letter, you acknowledge that you have read, understood, and agree to abide by all the terms and conditions stated therein.

Program Highlights:
• Real-world industry projects
• Mentorship from senior developers
• Performance-based stipend
• Certificate upon successful completion

If you have any questions, please contact us at hr@aparaitechsoftware.org or call +91-XXXXXXXXXX.

We look forward to having you on board!

Warm regards,
HR Department
Aparaitech Software Company
Baramati, Pune – 412306
info@aparaitechsoftware.org | www.aparaitech.org
"""
    msg.attach(MIMEText(body, 'plain'))

    part = MIMEBase('application', 'octet-stream')
    part.set_payload(pdf_buf.read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="{fname}"')
    msg.attach(part)

    with smtplib.SMTP(smtp_config['host'], smtp_config['port']) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_config['user'], smtp_config['pass'])
        server.sendmail(smtp_config['from'], to_email, msg.as_string())
