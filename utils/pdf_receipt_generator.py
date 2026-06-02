# utils/pdf_receipt_generator.py
import io
import hashlib
import datetime
from num2words import num2words
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph, 
                                Spacer, Image, HRFlowable)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
import qrcode
import streamlit as st
from supabase import create_client

# ==============================================================================
# 1. HELPERS
# ==============================================================================
def format_inr(cents):
    """Converts paise to formatted INR string."""
    if cents is None: return "0.00"
    return f"{float(cents)/100:,.2f}"

def get_amount_in_words(amount_cents):
    """Converts paise to Indian Rupees in words."""
    rupees = float(amount_cents) / 100
    try:
        # en_IN handles Lakhs/Crores correctly
        words = num2words(int(rupees), lang='en_IN').replace('rupee', 'Rupee').replace('rupees', 'Rupees')
        paise = int(round((rupees - int(rupees)) * 100))
        if paise > 0:
            paise_words = num2words(paise, lang='en_IN').replace('paisa', 'Paisa').replace('paise', 'Paise')
            return f"{words.title()} and {paise_words.title()} Only"
        return f"{words.title()} Only"
    except Exception:
        return "Amount in words could not be calculated."

def generate_receipt_number(supabase_client):
    """Generates SH-PAYOUT-YYYYMM-000001 sequentially."""
    today = datetime.datetime.now()
    prefix = f"SH-PAYOUT-{today.strftime('%Y%m')}"
    
    res = supabase_client.table('payout_receipts').select('receipt_number')\
        .like('receipt_number', f'{prefix}-%').order('receipt_number', desc=True).limit(1).execute()
    
    if res.data:
        last_num = int(res.data[0]['receipt_number'].split('-')[-1])
        new_num = last_num + 1
    else:
        new_num = 1
        
    return f"{prefix}-{str(new_num).zfill(6)}"

def generate_receipt_hash(receipt_number, payout_id, creator_id, net_amount):
    """Generates a SHA256 hash for tamper-proofing."""
    payload = f"{receipt_number}|{payout_id}|{creator_id}|{net_amount}"
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()

# ==============================================================================
# 2. PDF BUILDER
# ==============================================================================
def build_receipt_pdf(payout, creator, company, receipt_number, receipt_hash):
    """Builds the PDF in memory and returns the PDF bytes."""
    buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    styles = getSampleStyleSheet()
    
    # Custom Styles
    styles.add(ParagraphStyle(name='DocTitle', parent=styles['Title'], fontSize=20, textColor=colors.HexColor('#1A202C'), spaceAfter=6))
    styles.add(ParagraphStyle(name='SectionHeader', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#2D3748'), spaceAfter=4, borderWidth=1, borderColor=colors.HexColor('#CBD5E0'), borderPadding=4))
    styles.add(ParagraphStyle(name='SmallText', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#4A5568')))
    styles.add(ParagraphStyle(name='TableHeader', parent=styles['Normal'], fontSize=9, textColor=colors.white, fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='TableCell', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#2D3748')))
    styles.add(ParagraphStyle(name='Disclaimer', parent=styles['Normal'], fontSize=7, textColor=colors.HexColor('#718096'), alignment=TA_CENTER))

    story = []

    # --- HEADER ---
    header_data = [
        [Paragraph(f"<b>{company['legal_name']}</b>", styles['Normal']), 
         Paragraph("<b>PAYOUT RECEIPT</b>", styles['DocTitle'])],
        [Paragraph(company['address'], styles['SmallText']), 
         Paragraph(f"Receipt No: {receipt_number}", styles['SectionHeader'])]
    ]
    header_table = Table(header_data, colWidths=[320, 180])
    header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('LINEBELOW', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E0'))]))
    story.append(header_table)
    story.append(Spacer(1, 15))

    # --- CREATOR DETAILS ---
    story.append(Paragraph("CREATOR DETAILS", styles['SectionHeader']))
    fin_info = creator.get('financial_info', {})
    
    creator_data = [
        ["Full Name:", fin_info.get('legal_name', creator.get('creator_handle', 'N/A')), "Creator ID:", creator.get('creator_code', 'N/A')],
        ["Email:", creator.get('email', 'N/A'), "Phone:", creator.get('phone_number', 'N/A')],
        ["PAN:", fin_info.get('pan_number', 'N/A'), "GSTIN:", fin_info.get('gstin', 'N/A')],
        ["Bank Account:", f"XXXX{fin_info.get('account_number_last4', 'N/A')}", "IFSC:", fin_info.get('ifsc', 'N/A')],
        ["UPI ID:", fin_info.get('upi_id', 'N/A'), "Username:", creator.get('creator_handle', 'N/A')]
    ]
    creator_table = Table(creator_data, colWidths=[90, 210, 90, 110])
    creator_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME', (2,0), (2,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F7FAFC')),
        ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#F7FAFC')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(creator_table)
    story.append(Spacer(1, 15))

    # --- PAYOUT BREAKDOWN ---
    story.append(Paragraph("PAYOUT & TAX BREAKDOWN", styles['SectionHeader']))
    
    gross = payout['gross_amount_inr']
    platform_fee = payout['platform_commission_inr']
    refunds = payout['refunds_deducted_inr']
    net = payout['creator_share_inr']
    
    breakdown_data = [
        ["Description", "Amount (INR)"],
        ["Gross Earnings (Donations)", format_inr(gross)],
        ["Less: Refunds Deducted", f"- {format_inr(refunds)}"],
        ["Adjusted Gross", format_inr(gross - refunds)],
        ["Less: Platform Commission (Service Fee)", f"- {format_inr(platform_fee)}"],
        ["Net Amount Payable to Creator", format_inr(net)],
    ]
    
    bd_table = Table(breakdown_data, colWidths=[400, 100])
    bd_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2D3748')),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('FONTNAME', (0,5), (-1,5), 'Helvetica-Bold'),
        ('BACKGROUND', (0,5), (-1,5), colors.HexColor('#EDF2F7')),
    ]))
    story.append(bd_table)
    story.append(Spacer(1, 15))

    # --- AMOUNT IN WORDS & QR CODE ---
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(f"SH-VERIFY:{receipt_number}|HASH:{receipt_hash[:16]}|NET:{net}")
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    qr_bytes = io.BytesIO()
    qr_img.save(qr_bytes, format='PNG')
    qr_bytes.seek(0)

    words_data = [
        [Paragraph(f"<b>Amount in Words:</b><br/>{get_amount_in_words(net)}", styles['TableCell']),
         Image(qr_bytes, width=80, height=80)]
    ]
    words_table = Table(words_data, colWidths=[420, 80])
    words_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E0'))]))
    story.append(words_table)
    story.append(Spacer(1, 20))

    # --- DISCLAIMERS & SIGNATURE ---
    story.append(Paragraph("This document is system-generated and does not require a physical signature.", styles['Disclaimer']))
    story.append(Paragraph("Taxes deducted and deposited as per applicable Indian tax laws. This receipt is issued for accounting and reconciliation purposes.", styles['Disclaimer']))
    story.append(Spacer(1, 30))

    sig_data = [
        ["", ""],
        ["", "________________________"],
        ["For STREAMHEART PRIVATE LIMITED", f"Authorized Signatory"]
    ]
    sig_table = Table(sig_data, colWidths=[300, 200])
    sig_table.setStyle(TableStyle([('ALIGN', (1,0), (1,-1), 'CENTER'), ('FONTNAME', (0,0), (-1,-1), 'Helvetica'), ('FONTSIZE', (0,0), (-1,-1), 8)]))
    story.append(sig_table)

    # Build PDF
    doc.build(story)
    return buffer.getvalue()

# ==============================================================================
# 3. UPLOAD TO SUPABASE
# ==============================================================================
def upload_receipt_to_supabase(supabase_client, pdf_bytes, receipt_number):
    """Uploads PDF to private bucket and returns the signed URL."""
    file_path = f"receipts/{receipt_number}.pdf"
    
    # Upload
    supabase_client.storage.from_('payout-receipts').upload(file_path, pdf_bytes, file_options={"content_type": "application/pdf"})
    
    # Generate Signed URL (valid for 1 year)
    signed_url_res = supabase_client.storage.from_('payout-receipts').create_signed_url(file_path, 365 * 24 * 60 * 60)
    return signed_url_res['signedURL']
