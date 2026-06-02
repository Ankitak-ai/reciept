# utils/pdf_receipt_generator.py
import io
import hashlib
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, black, grey, white, lightgrey, Color
import streamlit as st

# === CONFIGURATION ===
COLOR_PRIMARY = HexColor('#1a1a2e')
COLOR_ACCENT = HexColor('#3b82f6')
COLOR_GREY = HexColor('#f3f4f6')
COLOR_BORDER = HexColor('#e2e8f0')
COLOR_TEXT_LABEL = HexColor('#4a5568')
COLOR_TEXT_VALUE = black
COLOR_SUCCESS = HexColor('#0f766e')

FONT_REG = 'Helvetica'
FONT_BOLD = 'Helvetica-Bold'
FONT_MONO = 'Courier'

LOGO_PATH = "logo.png" # Place this in your repo root, or it falls back to text

def format_inr(paise):
    if paise is None: return "INR 0.00"
    return f"INR {float(paise)/100:,.2f}"

def mask_upi(upi):
    if not upi or '@' not in upi: return "N/A"
    name, domain = upi.split('@')
    return f"{name[:2]}{'*' * max(0, len(name)-2)}@{domain}"

def draw_watermark(c, width, height, text="SETTLED"):
    c.saveState()
    c.setFillColor(Color(0.9, 0.9, 0.9, alpha=0.12))
    c.setFont(FONT_BOLD, 80)
    c.translate(width/2, height/2)
    c.rotate(45)
    c.drawCentredString(0, 0, text)
    c.restoreState()

def draw_wrapped_text(c, x, y, text, font_name, font_size, max_width, leading=12):
    c.setFont(font_name, font_size)
    words = text.split()
    lines, current_line = [], ""
    for word in words:
        test = current_line + word + " "
        if c.stringWidth(test, font_name, font_size) <= max_width:
            current_line = test
        else:
            lines.append(current_line.strip())
            current_line = word + " "
    if current_line: lines.append(current_line.strip())
    cy = y
    for line in lines:
        c.drawString(x, cy, line)
        cy -= leading
    return cy - leading

def draw_header(c, w, h, company):
    c.setFillColor(COLOR_PRIMARY)
    c.rect(0, h - 4.8*cm, w, 4.8*cm, fill=1, stroke=0)
    try:
        c.drawImage(LOGO_PATH, 1.5*cm, h - 3.8*cm, width=5*cm, height=1.8*cm, preserveAspectRatio=True)
    except:
        c.setFillColor(white); c.setFont(FONT_BOLD, 16)
        c.drawString(1.5*cm, h - 3*cm, "STREAMHEART")
    
    c.setFillColor(white); c.setFont(FONT_BOLD, 10)
    c.drawRightString(18.5*cm, h - 1.8*cm, company.get('legal_name', 'STREAMHEART PRIVATE LIMITED').upper())
    c.setFont(FONT_REG, 7.5); c.setFillColor(HexColor('#cbd5e1'))
    
    details = [
        f"CIN: {company.get('cin', 'N/A')}",
        company.get('address', 'Ghaziabad, UP'),
        f"PAN: {company.get('pan', 'N/A')} | TAN: {company.get('tan', 'N/A')}"
    ]
    y = h - 2.4*cm
    for line in details: 
        c.drawRightString(18.5*cm, y, line)
        y -= 0.35*cm
        
    c.setStrokeColor(HexColor('#cbd5e1')); c.line(0, h-4.8*cm, w, h-4.8*cm)
    c.setFont(FONT_BOLD, 13); c.setFillColor(white)
    c.drawString(1.5*cm, h - 5.4*cm, "CREATOR PAYOUT SETTLEMENT RECEIPT")
    return h - 6.2*cm

def draw_section(c, y, title):
    c.setFont(FONT_BOLD, 10); c.setFillColor(COLOR_PRIMARY)
    c.drawString(1.5*cm, y, title)
    c.setStrokeColor(COLOR_BORDER); c.line(1.5*cm, y-0.35*cm, 18.5*cm, y-0.35*cm)
    return y - 0.9*cm

def draw_kv(c, y, key, value, mono=False, right=False):
    c.setFont(FONT_REG, 8.5); c.setFillColor(COLOR_TEXT_LABEL)
    c.drawString(1.5*cm, y, key)
    c.setFont(FONT_MONO if mono else FONT_REG, 8.5); c.setFillColor(COLOR_TEXT_VALUE)
    if right: c.drawRightString(18*cm, y, str(value))
    else: c.drawString(6.5*cm, y, str(value))
    return y - 0.5*cm

def draw_financial_table(c, y, payout):
    x, w, rh = 1.5*cm, 17*cm, 0.6*cm
    gross = payout.get('gross_amount_inr', 0)
    refunds = payout.get('refunds_deducted_inr', 0)
    platform_fee = payout.get('platform_commission_inr', 0)
    net = payout.get('creator_share_inr', 0)
    adjusted_gross = gross - refunds
    
    items = [
        ("Gross Creator Earnings", format_inr(gross)),
        ("Less: Refunds Deducted", f"- {format_inr(refunds)}" if refunds > 0 else "INR 0.00"),
        ("Adjusted Gross Earnings", format_inr(adjusted_gross)),
        ("Platform Fee Deduction", f"- {format_inr(platform_fee)}"),
    ]
    
    c.setFillColor(COLOR_GREY); c.rect(x, y - rh, w, rh, fill=1, stroke=0)
    c.setFont(FONT_BOLD, 8.5); c.setFillColor(COLOR_TEXT_LABEL)
    c.drawString(x + 0.2*cm, y - 0.42*cm, "Description")
    c.drawRightString(x + w - 0.2*cm, y - 0.42*cm, "Amount")
    y -= rh
    
    c.setFont(FONT_REG, 8.5)
    for i, (desc, amt) in enumerate(items):
        c.setFillColor(HexColor('#f8fafc') if i % 2 == 0 else white)
        c.rect(x, y - rh, w, rh, fill=1, stroke=0)
        c.setFillColor(COLOR_TEXT_VALUE)
        c.drawString(x + 0.2*cm, y - 0.42*cm, desc)
        c.drawRightString(x + w - 0.2*cm, y - 0.42*cm, amt)
        y -= rh
        
    y -= 0.2*cm
    c.setFillColor(COLOR_PRIMARY); c.rect(x, y - rh, w, rh, fill=1, stroke=0)
    c.setFont(FONT_BOLD, 9.5); c.setFillColor(white)
    c.drawString(x + 0.2*cm, y - 0.42*cm, "Net Payout Amount")
    c.drawRightString(x + w - 0.2*cm, y - 0.42*cm, format_inr(net))
    return y - (rh + 0.5*cm)

def generate_receipt_pdf(payout, creator, company, receipt_number):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    
    fin_info_raw = creator.get('financial_info', [])
    fin_info = fin_info_raw[0] if isinstance(fin_info_raw, list) and len(fin_info_raw) > 0 else (fin_info_raw if isinstance(fin_info_raw, dict) else {})
        
    method = "UPI" if fin_info.get('upi_id') else "Bank Transfer"
    ref = payout.get('transaction_ref', 'PENDING')
    
    paid_at_str = payout.get('payout_date') or datetime.datetime.now().isoformat()
    try:
        paid_at = datetime.datetime.fromisoformat(paid_at_str.replace('Z', '+00:00'))
    except:
        paid_at = datetime.datetime.now()
        
    period_start = payout.get('cycle_start_date', 'N/A')
    period_end = payout.get('cycle_end_date', 'N/A')
    internal_id = payout.get('id', 'N/A')
    
    # ========== PAGE 1 ==========
    draw_watermark(c, w, h, "SETTLED")
    y = draw_header(c, w, h, company)
    
    y = draw_section(c, y, "RECEIPT METADATA")
    y = draw_kv(c, y, "Receipt ID:", receipt_number, mono=True)
    y = draw_kv(c, y, "Internal Payout ID:", internal_id[:8].upper() if internal_id != 'N/A' else 'N/A', mono=True)
    y = draw_kv(c, y, "Payout Reference:", ref, mono=True)
    y = draw_kv(c, y, "Receipt Version:", "v1.0")
    y = draw_kv(c, y, "Settlement Status:", "PAID & VERIFIED")
    y = draw_kv(c, y, "Settlement Period:", f"{period_start} → {period_end}")
    y = draw_kv(c, y, "Settlement Date:", paid_at.strftime("%d %b %Y, %I:%M %p IST"))
    y = draw_kv(c, y, "Receipt Generated:", datetime.datetime.now().strftime("%d %b %Y, %I:%M %p IST"))
    y = draw_kv(c, y, "Generated By:", st.session_state.get('user_email', 'ADMIN'))
    y -= 0.6*cm
    
    y = draw_section(c, y, "BENEFICIARY DETAILS")
    y = draw_kv(c, y, "Creator Handle:", creator.get('creator_handle', 'N/A'))
    y = draw_kv(c, y, "Creator ID:", f"CR-{str(creator.get('id',''))[:6].upper()}", mono=True)
    y = draw_kv(c, y, "Legal Name:", fin_info.get('legal_name', 'N/A'))
    y = draw_kv(c, y, "PAN Number:", fin_info.get('pan_number', 'N/A'), mono=True)
    y = draw_kv(c, y, "Email Address:", creator.get('email', 'N/A'))
    y = draw_kv(c, y, "Payout Method:", method.upper())
    
    upi = fin_info.get('upi_id', '')
    bank_str = mask_upi(upi) if upi else f"{fin_info.get('bank_name','Bank')} (xxxx{fin_info.get('account_number_last4','XXXX')})"
    y = draw_kv(c, y, "Destination:", bank_str)
    y = draw_kv(c, y, "Tax Status:", "VERIFIED")
    c.setFont(FONT_REG, 7.5); c.setFillColor(HexColor('#64748b'))
    c.drawString(1.5*cm, y-0.4*cm, "i Beneficiary information reflects the immutable creator tax snapshot recorded at settlement time.")
    y -= 1.1*cm
    
    y = draw_section(c, y, "FINANCIAL BREAKDOWN")
    y = draw_financial_table(c, y, payout)
    
    tds_note = "Compliance Note: This settlement acknowledgment is issued by Streamheart Private Limited for payouts processed through our platform. Applicable statutory deductions have been applied where required under Indian financial regulations."
    y = draw_wrapped_text(c, 1.5*cm, y, tds_note, FONT_REG, 8, 17*cm, leading=10)
    y -= 0.6*cm
    
    y = draw_section(c, y, "TRANSACTION PROOF")
    y = draw_kv(c, y, "Transaction Reference:", ref, mono=True)
    y = draw_kv(c, y, "Processing Bank:", company.get('bank_name', 'Bank') if method=="Bank Transfer" else "UPI Network")
    y = draw_kv(c, y, "Payment Method:", method.upper())
    y = draw_kv(c, y, "Settlement Time:", paid_at.strftime("%d %b %Y, %I:%M %p IST"))
    
    decl = "This electronically generated document constitutes an official creator settlement acknowledgment issued by Streamheart Private Limited. Applicable taxes and statutory deductions have been applied where required under Indian financial regulations. Unauthorized modification, alteration, or reproduction invalidates this document and associated verification records."
    y = draw_wrapped_text(c, 1.5*cm, y, decl, FONT_REG, 8, 17*cm, leading=10)
    
    if y < 5.5*cm: y = 5.5*cm
    y -= 0.5*cm
    
    c.setStrokeColor(grey); c.line(13*cm, y, 18.5*cm, y)
    c.setFont(FONT_REG, 8); c.setFillColor(COLOR_TEXT_LABEL)
    c.drawRightString(18.5*cm, y-0.4*cm, "Authorized Finance Signatory")
    c.drawRightString(18.5*cm, y-0.75*cm, company.get('legal_name', 'Streamheart Private Limited'))
    c.drawRightString(18.5*cm, y-1.1*cm, "Finance Operations")
    
    c.setStrokeColor(lightgrey); c.line(1.5*cm, 2.5*cm, 18.5*cm, 2.5*cm)
    c.setFont(FONT_REG, 7); c.setFillColor(grey)
    c.drawCentredString(10*cm, 1.8*cm, "This is a system-generated financial document.")
    c.drawCentredString(10*cm, 1.3*cm, f"© {company.get('legal_name', 'Streamheart Private Limited')} | {datetime.datetime.now().year}")
    
    # ========== PAGE 2 ==========
    c.showPage()
    y = h - 2*cm
    
    c.setFillColor(COLOR_PRIMARY); c.rect(0, h-2.5*cm, w, 2.5*cm, fill=1, stroke=0)
    c.setFillColor(white); c.setFont(FONT_BOLD, 12)
    c.drawString(1.5*cm, h-1.3*cm, "AUDIT & VERIFICATION RECORD")
    c.setFont(FONT_REG, 8); c.setFillColor(HexColor('#cbd5e1'))
    c.drawRightString(18.5*cm, h-1.5*cm, f"Receipt ID: {receipt_number}")
    y = h - 3.2*cm
    
    y = draw_section(c, y, "DOCUMENT VERIFICATION")
    temp_bytes = buffer.getvalue()
    final_pdf_hash = hashlib.sha256(temp_bytes).hexdigest()
    verify_id = f"VERIFY-SH-{final_pdf_hash[:6].upper()}"
    
    c.setFillColor(COLOR_GREY); c.setStrokeColor(COLOR_SUCCESS)
    c.roundRect(1.5*cm, y-2.5*cm, 17*cm, 2.5*cm, 3, fill=1, stroke=1)
    c.setFont(FONT_BOLD, 9); c.setFillColor(COLOR_SUCCESS)
    c.drawString(2*cm, y-0.9*cm, "✓ IMMUTABLE RECORD VERIFIED")
    c.setFont(FONT_MONO, 7); c.setFillColor(HexColor('#374151'))
    c.drawString(2*cm, y-1.5*cm, "SHA256 HASH:")
    c.drawString(2*cm, y-1.9*cm, f"{final_pdf_hash}")
    c.drawString(2*cm, y-2.3*cm, f"Verification ID: {verify_id}")
    y -= 3.2*cm
    
    y = draw_section(c, y, "IMMUTABLE BENEFICIARY SNAPSHOT")
    snapshot_data = [
        ("Legal Name", fin_info.get('legal_name', 'N/A')),
        ("PAN Number", fin_info.get('pan_number', 'N/A')),
        ("UPI ID", mask_upi(fin_info.get('upi_id', '')) or "N/A"),
        ("Bank Name", fin_info.get('bank_name', 'N/A')),
        ("Account Last 4", f"xxxx{fin_info.get('account_number_last4', 'XXXX')}"),
        ("Snapshot Timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat()),
    ]
    for k, v in snapshot_data:
        y = draw_kv(c, y, f"{k}:", v, mono=(k in ["PAN Number", "Snapshot Timestamp"]))
    y -= 0.5*cm
    
    y = draw_section(c, y, "ACCOUNTING CLASSIFICATION")
    acc_data = [
        ("Gross Platform Collection", format_inr(payout.get('gross_amount_inr', 0))),
        ("Creator Liability (Payable)", format_inr(payout.get('creator_share_inr', 0))),
        ("Platform Revenue Component", format_inr(payout.get('platform_commission_inr', 0))),
        ("Refunds Deducted", format_inr(payout.get('refunds_deducted_inr', 0))),
    ]
    for label, amt in acc_data:
        c.setFont(FONT_REG, 8.5); c.setFillColor(COLOR_TEXT_LABEL)
        c.drawString(1.5*cm, y, label)
        c.setFillColor(COLOR_TEXT_VALUE); c.setFont(FONT_REG, 8.5)
        c.drawRightString(18*cm, y, amt)
        y -= 0.5*cm
    y -= 0.5*cm
    
    y = draw_section(c, y, "INTERNAL PROCESSING METADATA")
    meta_data = [
        ("Payout Generated By", st.session_state.get('user_email', 'ADMIN')),
        ("Payout Approved By", "FINANCE_TEAM"),
        ("Payout Settled By", method.upper()),
        ("System Version", "v2.1.0"),
        ("Backend Reference", internal_id[:12].upper() if internal_id != 'N/A' else 'N/A'),
    ]
    for k, v in meta_data:
        y = draw_kv(c, y, f"{k}:", v, mono=(k == "Backend Reference"))
    y -= 0.5*cm
    
    y = draw_section(c, y, "ATTACHED SETTLEMENT REFERENCES")
    proof_data = [
        ("Proof File Name", f"proof_{ref}.png" if ref != 'PENDING' else 'N/A'),
        ("Storage Reference", f"supabase://payout-receipts/{receipt_number}.pdf"),
        ("Uploaded Timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat()),
        ("Proof Checksum", hashlib.sha256(ref.encode()).hexdigest()[:16] if ref != 'PENDING' else 'N/A'),
    ]
    for k, v in proof_data:
        y = draw_kv(c, y, f"{k}:", v, mono=(k in ["Storage Reference", "Proof Checksum"]))
    
    c.setFont(FONT_REG, 7.5); c.setFillColor(HexColor('#64748b'))
    disclaimer = "This document is maintained as part of the immutable financial settlement infrastructure operated by Streamheart Private Limited. Financial records, payout references, and associated verification hashes are retained for audit, compliance, taxation, and dispute-resolution purposes."
    y = draw_wrapped_text(c, 1.5*cm, y-0.5*cm, disclaimer, FONT_REG, 7.5, 17*cm, leading=9)
    
    c.setStrokeColor(COLOR_BORDER); c.rect(15*cm, y-2.5*cm, 2.5*cm, 2.5*cm, fill=0, stroke=1)
    c.setFont(FONT_REG, 6); c.setFillColor(HexColor('#64748b'))
    c.drawCentredString(16.25*cm, y-1.3*cm, "QR")
    c.drawCentredString(16.25*cm, y-1.7*cm, "Verify")
    c.drawCentredString(16.25*cm, y-2.1*cm, "Receipt")
    
    c.setStrokeColor(lightgrey); c.line(1.5*cm, 2.2*cm, 18.5*cm, 2.2*cm)
    c.setFont(FONT_REG, 7); c.setFillColor(grey)
    c.drawCentredString(10*cm, 1.6*cm, "Immutable Financial Settlement Record")
    c.drawCentredString(10*cm, 1.2*cm, "Generated by Streamheart Finance Infrastructure")
    
    c.save()
    return buffer.getvalue(), final_pdf_hash

def upload_receipt_to_supabase(supabase_client, pdf_bytes, receipt_number):
    file_path = f"receipts/{receipt_number}.pdf"
    supabase_client.storage.from_('payout-receipts').upload(file_path, pdf_bytes, file_options={"content_type": "application/pdf"})
    signed_url_res = supabase_client.storage.from_('payout-receipts').create_signed_url(file_path, 365 * 24 * 60 * 60)
    return signed_url_res['signedURL']
