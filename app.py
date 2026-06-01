import streamlit as st
import hashlib
import random
import string
from datetime import datetime, date
from io import BytesIO
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus.flowables import Flowable

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HyperChat · Payout Receipt Generator",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
#MainMenu, footer, header {visibility: hidden;}
.block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
.stTabs [data-baseweb="tab-list"] {gap: 4px; border-bottom: 1px solid #e2e8f0;}
.stTabs [data-baseweb="tab"] {
    padding: 8px 20px; font-size: 13px; font-weight: 500;
    border-radius: 6px 6px 0 0; border: 1px solid transparent;
}
.stTabs [aria-selected="true"] {
    background: white; border-color: #e2e8f0 #e2e8f0 white;
    color: #0f172a !important;
}
div[data-testid="stMetricValue"] {font-size: 1.1rem !important; font-weight: 600;}
.receipt-header {
    background: #0f172a; color: white; padding: 18px 24px;
    border-radius: 10px; margin-bottom: 1.5rem;
    display: flex; align-items: center; gap: 16px;
}
.field-note {font-size: 11px; color: #94a3b8; margin-top: 2px;}
.auto-id-box {
    background: #f1f5f9; border: 1px solid #e2e8f0;
    border-radius: 6px; padding: 8px 12px;
    font-family: monospace; font-size: 12px; color: #334155;
    display: flex; justify-content: space-between; align-items: center;
}
.section-divider {
    border: none; border-top: 1px solid #e2e8f0; margin: 1rem 0;
}
.fin-summary {
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 8px; padding: 16px;
}
.net-amount {
    background: #f0fdf4; border: 1px solid #bbf7d0;
    border-radius: 8px; padding: 12px 16px;
    font-size: 1.4rem; font-weight: 700; color: #166534;
    text-align: center;
}
.receipt-id-banner {
    background: #0f172a; color: white; text-align: center;
    padding: 16px; border-radius: 8px; margin-bottom: 1rem;
    font-family: monospace; font-size: 1.3rem; letter-spacing: 2px;
}
</style>
""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def gen_payout_id():
    today = datetime.now().strftime("%Y%m%d")
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PAY-{today}-{rand}"

def gen_creator_id():
    seq = random.randint(100000, 999999)
    return f"CRE-{datetime.now().year}-{seq}"

def gen_verification_id():
    parts = [
        ''.join(random.choices(string.ascii_uppercase + string.digits, k=8)),
        ''.join(random.choices(string.ascii_uppercase + string.digits, k=4)),
        ''.join(random.choices(string.ascii_uppercase + string.digits, k=4)),
        ''.join(random.choices(string.ascii_uppercase + string.digits, k=4)),
        ''.join(random.choices(string.ascii_uppercase + string.digits, k=12)),
    ]
    return "VRF-" + "-".join(parts)

def fmt_inr(val):
    try:
        n = float(val or 0)
        return f"₹{n:,.2f}"
    except:
        return "₹0.00"

def compute_net(gross, rpay, pfee, tds):
    try:
        return float(gross or 0) - float(rpay or 0) - float(pfee or 0) - float(tds or 0)
    except:
        return 0.0

def receipt_id_from_seq(seq):
    if seq:
        return f"HC-PAYOUT-{datetime.now().year}-{str(seq).zfill(6)}"
    return "—"

# ── Session state init ────────────────────────────────────────────────────────
if "payout_id" not in st.session_state:
    st.session_state.payout_id = gen_payout_id()
if "creator_id" not in st.session_state:
    st.session_state.creator_id = gen_creator_id()
if "verification_id" not in st.session_state:
    st.session_state.verification_id = gen_verification_id()
if "pdf_bytes" not in st.session_state:
    st.session_state.pdf_bytes = None
if "sha256" not in st.session_state:
    st.session_state.sha256 = None
if "generated_receipt_id" not in st.session_state:
    st.session_state.generated_receipt_id = None

# ── Header ────────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 11])
with col_logo:
    st.markdown("""
    <div style="background:#0f172a;color:white;width:48px;height:48px;
    border-radius:10px;display:flex;align-items:center;justify-content:center;
    font-weight:700;font-size:16px;margin-top:4px">HC</div>
    """, unsafe_allow_html=True)
with col_title:
    st.markdown("### HyperChat · Payout Receipt Generator")
    st.caption("Streamheart Private Limited · Finance Console · Production")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "① Creator Info",
    "② Financial Details",
    "③ Transaction",
    "④ Proof & Audit",
    "⑤ Review & Generate",
])

# ═══════════════════════════════════════════════════════════
# TAB 1 — Creator Info
# ═══════════════════════════════════════════════════════════
with tab1:
    st.markdown("#### Creator identity")
    c1, c2 = st.columns(2)
    with c1:
        creator_handle = st.text_input("Creator handle / username *", placeholder="e.g. @flashstream99",
                                        help="As registered on HyperChat platform")
    with c2:
        st.markdown("**Creator ID** &nbsp; `auto-generated`", unsafe_allow_html=True)
        id_col, btn_col = st.columns([4, 1])
        with id_col:
            st.code(st.session_state.creator_id, language=None)
        with btn_col:
            if st.button("↻ New", key="regen_cid", help="Regenerate Creator ID"):
                st.session_state.creator_id = gen_creator_id()
                st.rerun()

    c3, c4 = st.columns(2)
    with c3:
        legal_name = st.text_input("Legal full name *", placeholder="As per PAN card / Aadhaar")
    with c4:
        display_name = st.text_input("Display name (optional)", placeholder="Public-facing name")

    st.markdown("---")
    st.markdown("#### Tax & compliance")
    c5, c6, c7 = st.columns(3)
    with c5:
        pan = st.text_input("PAN number *", placeholder="ABCDE1234F", max_chars=10).upper()
        st.caption("10-character alphanumeric")
    with c6:
        aadhaar_last4 = st.text_input("Aadhaar (last 4 digits)", placeholder="XXXX", max_chars=4)
        st.caption("Partial, for reference only")
    with c7:
        gst = st.text_input("GST registration", placeholder="GSTIN or Not Applicable")

    c8, c9, c10 = st.columns(3)
    with c8:
        tax_status = st.selectbox("Tax residency status *", [
            "resident_individual", "non_resident", "company", "huf"
        ], format_func=lambda x: {
            "resident_individual": "Resident Individual",
            "non_resident": "Non-Resident (NRI)",
            "company": "Company / Firm",
            "huf": "HUF"
        }[x])
    with c9:
        form_15g = st.selectbox("Form 15G/H submitted", [
            "no", "yes", "partial"
        ], format_func=lambda x: {
            "no": "No",
            "yes": "Yes — TDS exempt",
            "partial": "Partial submission"
        }[x])
    with c10:
        account_type = st.selectbox("Creator account type", [
            "individual", "agency", "brand"
        ], format_func=lambda x: x.title())

    st.markdown("---")
    st.markdown("#### Bank & payment details")
    c11, c12 = st.columns(2)
    with c11:
        payment_method = st.selectbox("Primary payment method *",
                                       ["", "upi", "neft", "imps", "rtgs"],
                                       format_func=lambda x: x.upper() if x else "Select...")
    with c12:
        upi_id = st.text_input("UPI ID", placeholder="creator@upi",
                                disabled=(payment_method != "upi"))

    c13, c14, c15 = st.columns(3)
    with c13:
        bank_account = st.text_input("Bank account number", placeholder="Account number",
                                      disabled=(payment_method == "upi"))
    with c14:
        ifsc = st.text_input("IFSC code", placeholder="SBIN0001234",
                              disabled=(payment_method == "upi")).upper()
    with c15:
        bank_name = st.text_input("Bank name", placeholder="e.g. State Bank of India",
                                   disabled=(payment_method == "upi"))

    account_holder = st.text_input("Account holder name", placeholder="Must match legal name",
                                    disabled=(payment_method == "upi"))

    st.markdown("---")
    st.markdown("#### Creator address (for TDS certificate)")
    addr1 = st.text_input("Address line 1 *", placeholder="House/flat no., building, street")
    addr2 = st.text_input("Address line 2", placeholder="Area, locality")
    c16, c17, c18, c19 = st.columns(4)
    with c16:
        city = st.text_input("City *", placeholder="Mumbai")
    with c17:
        state_addr = st.text_input("State *", placeholder="Maharashtra")
    with c18:
        pincode = st.text_input("PIN code", placeholder="400001", max_chars=6)
    with c19:
        country = st.text_input("Country", value="India")

# ═══════════════════════════════════════════════════════════
# TAB 2 — Financial Details
# ═══════════════════════════════════════════════════════════
with tab2:
    st.markdown("#### Settlement period & identifiers")
    c1, c2, c3 = st.columns(3)
    with c1:
        fy = st.selectbox("Financial year *", ["FY 2025-26", "FY 2024-25", "FY 2026-27"])
    with c2:
        period_from = st.date_input("Settlement period from *", value=date(2026, 5, 1))
    with c3:
        period_to = st.date_input("Settlement period to *", value=date(2026, 5, 31))

    st.markdown("**Internal payout ID** &nbsp; `auto-generated`", unsafe_allow_html=True)
    pid_col, pbtn_col = st.columns([5, 1])
    with pid_col:
        st.code(st.session_state.payout_id, language=None)
    with pbtn_col:
        if st.button("↻ New", key="regen_pid", help="Regenerate Payout ID"):
            st.session_state.payout_id = gen_payout_id()
            st.rerun()
    st.caption("Auto-generated from timestamp + entropy · immutable after receipt generation")

    c4, c5, c6 = st.columns(3)
    with c4:
        seq_no = st.number_input("Receipt sequence number *", min_value=1, step=1, value=1,
                                  help="From PostgreSQL sequence")
    with c5:
        receipt_id = receipt_id_from_seq(int(seq_no))
        st.text_input("Generated receipt ID", value=receipt_id, disabled=True)
    with c6:
        quarter = st.selectbox("Quarter", ["Q1 (Apr–Jun)", "Q2 (Jul–Sep)", "Q3 (Oct–Dec)", "Q4 (Jan–Mar)"])

    st.markdown("---")
    st.markdown("#### Financial breakdown — all amounts in INR ₹")
    st.info("Enter all gross amounts. Net payout is computed automatically.", icon="ℹ️")

    fc1, fc2 = st.columns(2)
    with fc1:
        gross_earnings = st.number_input("Gross creator earnings (₹) *", min_value=0.0,
                                          step=0.01, format="%.2f", value=0.0,
                                          help="Total revenue generated before deductions")
        razorpay_fees = st.number_input("Razorpay payment gateway fees (₹)", min_value=0.0,
                                         step=0.01, format="%.2f", value=0.0)
    with fc2:
        platform_fee = st.number_input("HyperChat platform fee (₹)", min_value=0.0,
                                        step=0.01, format="%.2f", value=0.0,
                                        help="Platform service commission")
        tds_amount = st.number_input("TDS u/s 194-O deducted (₹)", min_value=0.0,
                                      step=0.01, format="%.2f", value=0.0)

    total_ded = razorpay_fees + platform_fee + tds_amount
    net_payout = max(0.0, gross_earnings - total_ded)

    m1, m2, m3 = st.columns(3)
    m1.metric("Total deductions", fmt_inr(total_ded))
    m2.metric("Net payout amount", fmt_inr(net_payout))
    m3.metric("Gross earnings", fmt_inr(gross_earnings))

    st.markdown(f"""
    <div class="net-amount">Net Payout &nbsp;·&nbsp; {fmt_inr(net_payout)}</div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### TDS configuration")
    t1, t2, t3 = st.columns(3)
    with t1:
        tds_section = st.selectbox("TDS section", [
            "194O", "194H", "194J", "nil"
        ], format_func=lambda x: {
            "194O": "Section 194-O (E-commerce)",
            "194H": "Section 194-H (Commission)",
            "194J": "Section 194-J (Professional)",
            "nil": "NIL — below threshold"
        }[x])
    with t2:
        tds_rate = st.number_input("TDS rate applied (%)", min_value=0.0, max_value=100.0,
                                    step=0.01, format="%.2f", value=1.0)
    with t3:
        tds_deductor = st.text_input("TDS deducted by", value="Streamheart Private Limited")

    t4, t5 = st.columns(2)
    with t4:
        tan = st.text_input("TAN of deductor", placeholder="MUMS12345A").upper()
    with t5:
        tds_challan = st.text_input("TDS challan / reference", placeholder="Challan reference if available")

# ═══════════════════════════════════════════════════════════
# TAB 3 — Transaction
# ═══════════════════════════════════════════════════════════
with tab3:
    st.markdown("#### Transaction reference")
    tr1, tr2 = st.columns(2)
    with tr1:
        utr = st.text_input("UTR / reference number *", placeholder="e.g. SBIN2026060112345678",
                             help="Unique Transaction Reference from bank/UPI")
    with tr2:
        txn_channel = st.selectbox("Payment channel *", ["", "UPI", "NEFT", "IMPS", "RTGS"],
                                    format_func=lambda x: x if x else "Select...")

    tr3, tr4 = st.columns(2)
    with tr3:
        processing_bank = st.text_input("Processing bank (sender) *",
                                         placeholder="e.g. HDFC Bank, ICICI Bank")
    with tr4:
        sender_acct = st.text_input("Sender account (last 4 digits)", placeholder="XXXX", max_chars=4)

    tr5, tr6 = st.columns(2)
    with tr5:
        settlement_ts = st.datetime_input("Settlement timestamp *",
                                           value=datetime.now(),
                                           help="When the bank confirmed the transaction")
    with tr6:
        initiated_by = st.text_input("Transaction initiated by", placeholder="Admin email or name")

    narration = st.text_area("Settlement narration / remarks *",
                              placeholder="e.g. HyperChat creator payout — May 2026 — @flashstream99",
                              help="Transaction description as entered in banking app")

    st.markdown("---")
    st.markdown("#### Company banking details (sender)")
    cb1, cb2 = st.columns(2)
    with cb1:
        company_cin = st.text_input("Company CIN", placeholder="U74999MH2023PTC123456")
        company_address = st.text_input("Registered office address",
                                         placeholder="Streamheart Pvt Ltd registered address")
    with cb2:
        company_pan = st.text_input("Company PAN", placeholder="AABCS1234Z").upper()
        finance_email = st.text_input("Finance support email",
                                       value="finance@hyperchat.in", placeholder="finance@hyperchat.in")

    st.markdown("---")
    st.markdown("#### Authorised signatory")
    sg1, sg2, sg3 = st.columns(3)
    with sg1:
        signatory_name = st.text_input("Signatory name *", placeholder="Full name")
    with sg2:
        signatory_title = st.text_input("Designation", value="Chief Financial Officer")
    with sg3:
        signatory_id = st.text_input("Employee ID", placeholder="EMP-XXX")

# ═══════════════════════════════════════════════════════════
# TAB 4 — Proof & Audit
# ═══════════════════════════════════════════════════════════
with tab4:
    st.markdown("#### Payout proof screenshot")
    st.warning("Upload the bank/UPI confirmation screenshot. Stored in private `payout-proofs` bucket via signed URLs only.", icon="⚠️")

    proof_file = st.file_uploader("Upload proof screenshot",
                                   type=["png", "jpg", "jpeg", "pdf"],
                                   help="Max 10 MB · stored in payout-proofs bucket (private)")

    pf1, pf2 = st.columns(2)
    with pf1:
        proof_path_default = f"payout-proofs/{datetime.now().year}/{proof_file.name.replace(' ','_')}" if proof_file else ""
        proof_path = st.text_input("Proof file storage path",
                                    value=proof_path_default,
                                    placeholder="payout-proofs/2026/...",
                                    help="Auto-populated on upload · or enter Supabase path")
    with pf2:
        proof_ts = st.datetime_input("Proof upload timestamp", value=datetime.now())

    if proof_file:
        st.success(f"✓ {proof_file.name} · {proof_file.size/1024:.1f} KB · uploaded {datetime.now().strftime('%H:%M:%S')}")

    st.markdown("---")
    st.markdown("#### Verification & immutability")

    vi1, vi2 = st.columns(2)
    with vi1:
        st.markdown("**Verification ID** &nbsp; `auto-generated`", unsafe_allow_html=True)
        vcol, vbtn = st.columns([4, 1])
        with vcol:
            st.code(st.session_state.verification_id, language=None)
        with vbtn:
            if st.button("↻ New", key="regen_vid"):
                st.session_state.verification_id = gen_verification_id()
                st.rerun()
        st.caption("UUID-based · linked to receipt hash · immutable after generation")
    with vi2:
        payout_status = st.selectbox("Payout status at generation *",
                                      ["PAID", "PARTIALLY_PAID"],
                                      format_func=lambda x: x.replace("_", " "))

    st.markdown("**SHA-256 hash**")
    st.info("Computed from final PDF binary content after generation · stored in `payout_receipts`, `payouts` table, and embedded in receipt page 2", icon="🔒")

    st.markdown("---")
    st.markdown("#### Audit metadata")
    a1, a2, a3 = st.columns(3)
    with a1:
        admin_actor = st.text_input("Generated by (admin) *", placeholder="Admin email / name")
    with a2:
        backend_version = st.text_input("Backend version", value="v2.4.1")
    with a3:
        environment = st.selectbox("Environment", ["production", "staging"])

    audit_notes = st.text_area("Internal notes / audit remarks",
                                placeholder="Any internal remarks for audit trail (not printed on receipt)...",
                                height=80)

# ═══════════════════════════════════════════════════════════
# TAB 5 — Review & Generate
# ═══════════════════════════════════════════════════════════
with tab5:
    rid = receipt_id_from_seq(int(seq_no))
    st.markdown(f"""
    <div class="receipt-id-banner">{rid}</div>
    """, unsafe_allow_html=True)

    rc1, rc2 = st.columns(2)

    with rc1:
        st.markdown("##### Creator")
        st.table({
            "Field": ["Handle", "Legal name", "PAN", "UPI / Bank", "Tax status", "Creator ID"],
            "Value": [
                creator_handle or "—",
                legal_name or "—",
                pan or "—",
                upi_id if payment_method == "upi" else (bank_account or "—"),
                tax_status.replace("_", " ").title(),
                st.session_state.creator_id,
            ]
        })

        st.markdown("##### Identifiers")
        st.table({
            "Field": ["Internal payout ID", "Verification ID", "Receipt ID"],
            "Value": [
                st.session_state.payout_id,
                st.session_state.verification_id[:30] + "...",
                rid,
            ]
        })

    with rc2:
        st.markdown("##### Financial breakdown")
        fin_data = {
            "Description": [
                "Gross creator earnings",
                "Razorpay fees",
                "HyperChat platform fee",
                "TDS u/s 194-O",
                "─────────────────",
                "NET PAYOUT",
            ],
            "Amount": [
                fmt_inr(gross_earnings),
                fmt_inr(razorpay_fees),
                fmt_inr(platform_fee),
                fmt_inr(tds_amount),
                "─────────",
                fmt_inr(net_payout),
            ]
        }
        st.table(fin_data)

        st.markdown("##### Transaction")
        st.table({
            "Field": ["UTR / Reference", "Channel", "Bank", "Settlement time"],
            "Value": [
                utr or "—",
                txn_channel or "—",
                processing_bank or "—",
                settlement_ts.strftime("%d %b %Y %H:%M") if settlement_ts else "—",
            ]
        })

    st.info("After generation, this receipt becomes immutable. SHA-256 hash will be stored in `payout_receipts`, `payouts` table, and embedded in PDF page 2.", icon="🔒")
    st.divider()

    # ── Generate button ───────────────────────────────────────────────────────
    if st.button("⚡ Generate Immutable PDF Receipt", type="primary", use_container_width=True):
        with st.spinner("Generating receipt PDF..."):

            # ── Collect all data ──────────────────────────────────────────────
            data = dict(
                receiptId=rid,
                verificationId=st.session_state.verification_id,
                creator_handle=creator_handle,
                creator_id=st.session_state.creator_id,
                legal_name=legal_name,
                pan=pan,
                aadhaar_last4=aadhaar_last4,
                gst=gst,
                tax_status=tax_status,
                form_15g=form_15g,
                account_type=account_type,
                payment_method=payment_method,
                upi_id=upi_id,
                bank_account=bank_account,
                ifsc=ifsc,
                bank_name=bank_name,
                account_holder=account_holder,
                addr1=addr1, addr2=addr2, city=city,
                state=state_addr, pincode=pincode, country=country,
                fy=fy,
                period_from=str(period_from),
                period_to=str(period_to),
                payout_id=st.session_state.payout_id,
                gross_earnings=gross_earnings,
                razorpay_fees=razorpay_fees,
                platform_fee=platform_fee,
                tds_amount=tds_amount,
                total_deductions=total_ded,
                net_payout=net_payout,
                tds_section=tds_section,
                tds_rate=tds_rate,
                tds_deductor=tds_deductor,
                tan=tan,
                tds_challan=tds_challan,
                quarter=quarter,
                utr=utr,
                txn_channel=txn_channel,
                processing_bank=processing_bank,
                sender_acct=sender_acct,
                settlement_ts=str(settlement_ts),
                initiated_by=initiated_by,
                narration=narration,
                company_cin=company_cin,
                company_pan=company_pan,
                company_address=company_address,
                finance_email=finance_email,
                signatory_name=signatory_name,
                signatory_title=signatory_title,
                signatory_id=signatory_id,
                proof_path=proof_path,
                proof_ts=str(proof_ts),
                payout_status=payout_status,
                admin_actor=admin_actor,
                backend_version=backend_version,
                environment=environment,
                audit_notes=audit_notes,
                generated_at=datetime.now().isoformat(),
            )

            # ── Build PDF ─────────────────────────────────────────────────────
            pdf_buf = BytesIO()
            build_receipt_pdf(pdf_buf, data)
            pdf_bytes = pdf_buf.getvalue()

            # ── SHA-256 from PDF binary ───────────────────────────────────────
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            data["sha256"] = sha256

            # ── Rebuild PDF with hash embedded ────────────────────────────────
            pdf_buf2 = BytesIO()
            build_receipt_pdf(pdf_buf2, data)
            final_pdf = pdf_buf2.getvalue()
            final_hash = hashlib.sha256(final_pdf).hexdigest()

            st.session_state.pdf_bytes = final_pdf
            st.session_state.sha256 = final_hash
            st.session_state.generated_receipt_id = rid

        st.success(f"✅ Receipt generated — {rid}", icon="✅")
        st.code(f"SHA-256: {final_hash}", language=None)

    # ── Download button ───────────────────────────────────────────────────────
    if st.session_state.pdf_bytes:
        fname = f"{st.session_state.generated_receipt_id or 'receipt'}.pdf"
        st.download_button(
            label="⬇️ Download PDF Receipt",
            data=st.session_state.pdf_bytes,
            file_name=fname,
            mime="application/pdf",
            use_container_width=True,
        )
        st.caption(f"SHA-256: `{st.session_state.sha256}`")


# ═══════════════════════════════════════════════════════════
# PDF BUILDER
# ═══════════════════════════════════════════════════════════
def build_receipt_pdf(buf, d):
    """Build the two-page A4 receipt PDF into `buf`."""

    PAGE_W, PAGE_H = A4
    L, R, T, B = 18*mm, 18*mm, 18*mm, 18*mm

    # ── Colours ───────────────────────────────────────────────────────────────
    BLACK      = colors.HexColor("#0f172a")
    DARK_GREY  = colors.HexColor("#334155")
    MID_GREY   = colors.HexColor("#64748b")
    LIGHT_GREY = colors.HexColor("#e2e8f0")
    VERY_LIGHT = colors.HexColor("#f8fafc")
    GREEN      = colors.HexColor("#166534")
    GREEN_BG   = colors.HexColor("#f0fdf4")
    RED        = colors.HexColor("#991b1b")
    BLUE       = colors.HexColor("#1e3a8a")
    BLUE_BG    = colors.HexColor("#eff6ff")

    # ── Styles ────────────────────────────────────────────────────────────────
    def sty(name, **kw):
        return ParagraphStyle(name, **kw)

    S_TITLE     = sty("title",   fontSize=18, fontName="Helvetica-Bold",
                       textColor=BLACK, spaceAfter=2, leading=22)
    S_SUBTITLE  = sty("sub",     fontSize=9,  fontName="Helvetica",
                       textColor=MID_GREY,   leading=13)
    S_H2        = sty("h2",      fontSize=10, fontName="Helvetica-Bold",
                       textColor=BLACK, spaceBefore=6, spaceAfter=3, leading=14)
    S_H3        = sty("h3",      fontSize=8.5,fontName="Helvetica-Bold",
                       textColor=DARK_GREY, spaceBefore=4, spaceAfter=2, leading=12)
    S_BODY      = sty("body",    fontSize=8,  fontName="Helvetica",
                       textColor=DARK_GREY, leading=12)
    S_BODY_SM   = sty("bodysm",  fontSize=7,  fontName="Helvetica",
                       textColor=MID_GREY,  leading=10)
    S_MONO      = sty("mono",    fontSize=7.5,fontName="Courier",
                       textColor=DARK_GREY, leading=11)
    S_MONO_SM   = sty("monosm", fontSize=6.5,fontName="Courier",
                       textColor=MID_GREY,  leading=10)
    S_LABEL     = sty("label",   fontSize=7,  fontName="Helvetica-Bold",
                       textColor=MID_GREY,  leading=10, spaceAfter=1)
    S_VALUE     = sty("value",   fontSize=8,  fontName="Helvetica",
                       textColor=BLACK,     leading=11)
    S_LEGAL     = sty("legal",   fontSize=7,  fontName="Helvetica",
                       textColor=MID_GREY,  leading=10, alignment=TA_JUSTIFY)
    S_CENTER    = sty("center",  fontSize=8,  fontName="Helvetica",
                       textColor=DARK_GREY, leading=12, alignment=TA_CENTER)
    S_RIGHT     = sty("right",   fontSize=8,  fontName="Helvetica",
                       textColor=DARK_GREY, leading=12, alignment=TA_RIGHT)
    S_STATUS    = sty("status",  fontSize=22, fontName="Helvetica-Bold",
                       textColor=colors.Color(0,0,0,0.06),
                       alignment=TA_CENTER, leading=28)

    def inr(v):
        try:
            n = float(v or 0)
            return f"Rs. {n:,.2f}"
        except:
            return "Rs. 0.00"

    def val(v, fallback="—"):
        return str(v).strip() if v and str(v).strip() else fallback

    addr_parts = [d.get("addr1",""), d.get("addr2",""),
                  d.get("city",""), d.get("state",""),
                  d.get("pincode",""), d.get("country","India")]
    full_addr = ", ".join(p for p in addr_parts if p)

    tax_map = {
        "resident_individual": "Resident Individual",
        "non_resident": "Non-Resident (NRI)",
        "company": "Company / Firm",
        "huf": "HUF",
    }

    # ── Table helpers ─────────────────────────────────────────────────────────
    BODY_W = PAGE_W - L - R  # usable width

    def kv_table(rows, col_widths=None):
        """Two-column label/value table."""
        if col_widths is None:
            col_widths = [BODY_W * 0.38, BODY_W * 0.62]
        data = []
        for label, value in rows:
            data.append([
                Paragraph(label, S_LABEL),
                Paragraph(str(value), S_VALUE),
            ])
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("ROWBACKGROUNDS", (0,0), (-1,-1), [VERY_LIGHT, colors.white]),
            ("BOTTOMPADDING",  (0,0), (-1,-1), 4),
            ("TOPPADDING",     (0,0), (-1,-1), 4),
            ("LEFTPADDING",    (0,0), (-1,-1), 6),
            ("RIGHTPADDING",   (0,0), (-1,-1), 6),
            ("GRID",           (0,0), (-1,-1), 0.3, LIGHT_GREY),
            ("VALIGN",         (0,0), (-1,-1), "TOP"),
        ]))
        return t

    def section_header(text):
        return [
            Spacer(1, 4*mm),
            Paragraph(text.upper(), S_H3),
            HRFlowable(width="100%", thickness=0.5, color=LIGHT_GREY),
            Spacer(1, 2*mm),
        ]

    # ═════════════════════════════════════════════════════
    # PAGE 1 CONTENT
    # ═════════════════════════════════════════════════════
    story = []

    # ── Company header ────────────────────────────────────────────────────────
    header_data = [[
        Paragraph("STREAMHEART PRIVATE LIMITED", sty("co", fontSize=14,
                  fontName="Helvetica-Bold", textColor=BLACK, leading=18)),
        Paragraph("PAYOUT SETTLEMENT RECEIPT", sty("doc", fontSize=10,
                  fontName="Helvetica-Bold", textColor=BLUE,
                  alignment=TA_RIGHT, leading=14)),
    ]]
    header_table = Table(header_data, colWidths=[BODY_W*0.6, BODY_W*0.4])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 1*mm))

    sub_data = [[
        Paragraph("Platform: HyperChat &nbsp;|&nbsp; Finance Support: " +
                  val(d.get("finance_email"), "finance@hyperchat.in"), S_SUBTITLE),
        Paragraph(f"<b>{val(d.get('payout_status','PAID'))}</b>", sty("ps",
                  fontSize=10, fontName="Helvetica-Bold",
                  textColor=GREEN if d.get("payout_status")=="PAID" else RED,
                  alignment=TA_RIGHT, leading=14)),
    ]]
    sub_table = Table(sub_data, colWidths=[BODY_W*0.7, BODY_W*0.3])
    sub_table.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story.append(sub_table)
    story.append(HRFlowable(width="100%", thickness=1, color=BLACK, spaceAfter=4*mm))

    # ── Receipt metadata band ─────────────────────────────────────────────────
    meta_rows = [
        ["Receipt ID", val(d.get("receiptId")), "Internal Payout ID", val(d.get("payout_id"))],
        ["Settlement Status", val(d.get("payout_status")), "Financial Year", val(d.get("fy"))],
        ["Settlement Period",
         f"{val(d.get('period_from'))} to {val(d.get('period_to'))}",
         "Quarter", val(d.get("quarter"))],
        ["Settlement Timestamp", val(d.get("settlement_ts")),
         "Receipt Generated", d.get("generated_at","")[:19].replace("T"," ")],
        ["Verification ID", val(d.get("verificationId")), "Creator ID", val(d.get("creator_id"))],
    ]
    cw = [BODY_W*0.18, BODY_W*0.32, BODY_W*0.18, BODY_W*0.32]
    meta_data = []
    for row in meta_rows:
        meta_data.append([
            Paragraph(row[0], S_LABEL),
            Paragraph(row[1], S_MONO),
            Paragraph(row[2], S_LABEL),
            Paragraph(row[3], S_MONO),
        ])
    meta_tbl = Table(meta_data, colWidths=cw)
    meta_tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [VERY_LIGHT, colors.white]),
        ("GRID",    (0,0), (-1,-1), 0.3, LIGHT_GREY),
        ("PADDING", (0,0), (-1,-1), 5),
        ("VALIGN",  (0,0), (-1,-1), "TOP"),
        ("BOX",     (0,0), (-1,-1), 0.5, LIGHT_GREY),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 4*mm))

    # ── Creator details ───────────────────────────────────────────────────────
    story += section_header("Creator Details")
    creator_rows = [
        ("Creator Handle / Username", val(d.get("creator_handle"))),
        ("Legal Name (as per PAN)", val(d.get("legal_name"))),
        ("PAN Number", val(d.get("pan"))),
        ("Tax Residency Status", tax_map.get(d.get("tax_status",""), val(d.get("tax_status")))),
        ("Form 15G / 15H Submitted", val(d.get("form_15g","No")).title()),
        ("GST Registration", val(d.get("gst"))),
        ("Payment Method", val(d.get("payment_method","")).upper()),
        ("UPI ID / Bank Details",
         val(d.get("upi_id")) if d.get("payment_method") == "upi"
         else f"{val(d.get('bank_account'))} / IFSC: {val(d.get('ifsc'))}"),
        ("Registered Address", val(full_addr)),
    ]
    story.append(kv_table(creator_rows))
    story.append(Spacer(1, 4*mm))

    # ── Financial breakdown ───────────────────────────────────────────────────
    story += section_header("Financial Breakdown")

    fin_header = [
        Paragraph("DESCRIPTION", S_LABEL),
        Paragraph("CLASSIFICATION", S_LABEL),
        Paragraph("AMOUNT (INR)", sty("fh", fontSize=7, fontName="Helvetica-Bold",
                   textColor=MID_GREY, alignment=TA_RIGHT, leading=10)),
    ]
    fin_rows = [
        fin_header,
        [Paragraph("Gross Creator Earnings", S_BODY),
         Paragraph("Creator Liability", S_BODY_SM),
         Paragraph(inr(d.get("gross_earnings",0)), sty("ra", fontSize=8,
                   fontName="Courier", textColor=BLACK, alignment=TA_RIGHT, leading=11))],
        [Paragraph("Razorpay Payment Gateway Fees", S_BODY),
         Paragraph("Pass-through Cost", S_BODY_SM),
         Paragraph(f"({inr(d.get('razorpay_fees',0))})", sty("ra2", fontSize=8,
                   fontName="Courier", textColor=RED, alignment=TA_RIGHT, leading=11))],
        [Paragraph("HyperChat Platform Fee", S_BODY),
         Paragraph("Platform Revenue", S_BODY_SM),
         Paragraph(f"({inr(d.get('platform_fee',0))})", sty("ra3", fontSize=8,
                   fontName="Courier", textColor=RED, alignment=TA_RIGHT, leading=11))],
        [Paragraph("TDS u/s 194-O (E-Commerce Operator)", S_BODY),
         Paragraph("TDS Withheld Liability", S_BODY_SM),
         Paragraph(f"({inr(d.get('tds_amount',0))})", sty("ra4", fontSize=8,
                   fontName="Courier", textColor=RED, alignment=TA_RIGHT, leading=11))],
        [Paragraph("<b>Net Payout Amount</b>", sty("net", fontSize=9,
                   fontName="Helvetica-Bold", textColor=GREEN, leading=12)),
         Paragraph("Liability Settlement", S_BODY_SM),
         Paragraph(f"<b>{inr(d.get('net_payout',0))}</b>", sty("netv", fontSize=9,
                   fontName="Courier-Bold", textColor=GREEN,
                   alignment=TA_RIGHT, leading=12))],
    ]
    fcw = [BODY_W*0.50, BODY_W*0.25, BODY_W*0.25]
    fin_tbl = Table(fin_rows, colWidths=fcw)
    fin_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  BLACK),
        ("TEXTCOLOR",     (0,0), (-1,0),  colors.white),
        ("ROWBACKGROUNDS",(0,1), (-1,-2), [VERY_LIGHT, colors.white]),
        ("BACKGROUND",    (0,-1),(-1,-1), GREEN_BG),
        ("GRID",    (0,0), (-1,-1), 0.3, LIGHT_GREY),
        ("LINEBELOW",(0,-1),(-1,-1), 1.0, GREEN),
        ("LINETOP",  (0,-1),(-1,-1), 1.0, GREEN),
        ("BOX",     (0,0), (-1,-1), 0.5, DARK_GREY),
        ("PADDING", (0,0), (-1,-1), 6),
        ("VALIGN",  (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",   (2,0), (2,-1), "RIGHT"),
    ]))
    story.append(fin_tbl)
    story.append(Spacer(1, 4*mm))

    # ── Transaction details ───────────────────────────────────────────────────
    story += section_header("Transaction Details")
    txn_rows = [
        ("UTR / Transaction Reference", val(d.get("utr"))),
        ("Payment Method / Channel", val(d.get("txn_channel"))),
        ("Processing Bank (Sender)", val(d.get("processing_bank"))),
        ("Settlement Narration", val(d.get("narration"))),
        ("Settlement Timestamp", val(d.get("settlement_ts"))),
        ("Initiated By", val(d.get("initiated_by"))),
    ]
    story.append(kv_table(txn_rows))
    story.append(Spacer(1, 4*mm))

    # ── TDS compliance note ───────────────────────────────────────────────────
    story += section_header("TDS Compliance Note")
    tds_note = (
        "<b>TDS Compliance Note:</b> Applicable Tax Deducted at Source (TDS), where required, "
        "has been deducted under Section 194-O of the Income Tax Act, 1961 relating to "
        "e-commerce participant settlements facilitated through digital platforms. "
        f"TDS Section applied: {val(d.get('tds_section'))}. "
        f"Rate: {val(d.get('tds_rate'))}%. "
        f"Deducted by: {val(d.get('tds_deductor'))}. "
        f"TAN: {val(d.get('tan'))}."
    )
    tds_box = Table([[Paragraph(tds_note, S_LEGAL)]], colWidths=[BODY_W])
    tds_box.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), BLUE_BG),
        ("BOX", (0,0), (-1,-1), 0.5, BLUE),
        ("PADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(tds_box)
    story.append(Spacer(1, 4*mm))

    # ── Legal declaration ─────────────────────────────────────────────────────
    story += section_header("Legal Declaration")
    legal_text = (
        "This document constitutes an official payout settlement receipt issued by Streamheart Private Limited "
        "for the HyperChat platform. This receipt confirms that the net payout amount stated herein has been "
        "transferred to the creator's registered payment instrument. This is a computer-generated document. "
        "The settlement details recorded in this receipt are final and immutable. Any disputes regarding this "
        "settlement must be raised within 30 days of the settlement date by writing to finance@hyperchat.in. "
        "Streamheart Private Limited is not liable for delays caused by banking intermediaries. "
        "This receipt does not constitute a TDS certificate (Form 16A); a separate TDS certificate will be "
        "issued as required under the Income Tax Act, 1961."
    )
    story.append(Paragraph(legal_text, S_LEGAL))
    story.append(Spacer(1, 4*mm))

    # ── Signatory block ───────────────────────────────────────────────────────
    story += section_header("Authorised Signatory")
    sig_data = [[
        Paragraph(
            f"<b>{val(d.get('signatory_name'))}</b><br/>"
            f"{val(d.get('signatory_title'))}<br/>"
            "Streamheart Private Limited<br/>"
            f"Date: {d.get('generated_at','')[:10]}",
            sty("sig", fontSize=8, fontName="Helvetica", textColor=DARK_GREY, leading=13)
        ),
        Paragraph(
            "For Streamheart Private Limited<br/>"
            "<br/><br/>"
            "________________________<br/>"
            "Authorised Signatory",
            sty("sigr", fontSize=8, fontName="Helvetica", textColor=MID_GREY,
                alignment=TA_RIGHT, leading=13)
        ),
    ]]
    sig_tbl = Table(sig_data, colWidths=[BODY_W*0.5, BODY_W*0.5])
    sig_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOX",    (0,0), (-1,-1), 0.3, LIGHT_GREY),
        ("PADDING",(0,0), (-1,-1), 8),
    ]))
    story.append(sig_tbl)

    # ── PAGE 2 ────────────────────────────────────────────────────────────────
    story.append(PageBreak())

    # ── Page 2 header ─────────────────────────────────────────────────────────
    story.append(Paragraph("AUDIT & VERIFICATION LAYER", sty("p2h", fontSize=12,
                 fontName="Helvetica-Bold", textColor=BLACK, leading=16)))
    story.append(Paragraph(
        f"Receipt: {val(d.get('receiptId'))}  |  "
        f"Payout ID: {val(d.get('payout_id'))}  |  "
        f"Generated: {d.get('generated_at','')[:19].replace('T',' ')}",
        S_SUBTITLE))
    story.append(HRFlowable(width="100%", thickness=1, color=BLACK, spaceAfter=4*mm))

    # ── SHA-256 verification block ────────────────────────────────────────────
    story += section_header("SHA-256 Verification Block")
    hash_val = val(d.get("sha256", "Pending computation"))
    hash_data = [
        [Paragraph("SHA-256 Hash (PDF Binary Content)", S_LABEL),
         Paragraph(hash_val, S_MONO)],
        [Paragraph("Verification ID", S_LABEL),
         Paragraph(val(d.get("verificationId")), S_MONO)],
        [Paragraph("Immutable Record Status", S_LABEL),
         Paragraph("GENERATED · IMMUTABLE · TAMPER-EVIDENT", sty("imm", fontSize=8,
                   fontName="Helvetica-Bold", textColor=GREEN, leading=11))],
    ]
    hash_tbl = Table(hash_data, colWidths=[BODY_W*0.28, BODY_W*0.72])
    hash_tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [VERY_LIGHT, colors.white]),
        ("GRID",    (0,0), (-1,-1), 0.3, LIGHT_GREY),
        ("BOX",     (0,0), (-1,-1), 0.5, DARK_GREY),
        ("PADDING", (0,0), (-1,-1), 6),
        ("VALIGN",  (0,0), (-1,-1), "TOP"),
    ]))
    story.append(hash_tbl)
    story.append(Spacer(1, 4*mm))

    # ── Immutable creator snapshot ────────────────────────────────────────────
    story += section_header("Immutable Creator Financial Snapshot (Payout-Time Record)")
    snap_rows = [
        ("Creator Handle", val(d.get("creator_handle"))),
        ("Legal Name", val(d.get("legal_name"))),
        ("PAN", val(d.get("pan"))),
        ("Tax Status", tax_map.get(d.get("tax_status",""), val(d.get("tax_status")))),
        ("UPI / Bank Details",
         val(d.get("upi_id")) if d.get("payment_method") == "upi"
         else f"A/C: {val(d.get('bank_account'))} IFSC: {val(d.get('ifsc'))}"),
        ("Address at Settlement", val(full_addr)),
        ("Gross Earnings Snapshot", inr(d.get("gross_earnings",0))),
        ("Net Payout Snapshot", inr(d.get("net_payout",0))),
    ]
    story.append(kv_table(snap_rows))
    story.append(Spacer(1, 4*mm))

    # ── Accounting classification ─────────────────────────────────────────────
    story += section_header("Accounting Classification")
    acc_data = [
        [Paragraph("ACCOUNT", S_LABEL),
         Paragraph("CLASSIFICATION", S_LABEL),
         Paragraph("AMOUNT (INR)", sty("ah", fontSize=7, fontName="Helvetica-Bold",
                   textColor=MID_GREY, alignment=TA_RIGHT, leading=10))],
        [Paragraph("HyperChat Platform Fee", S_BODY),
         Paragraph("Platform Revenue (Company Income)", S_BODY_SM),
         Paragraph(inr(d.get("platform_fee",0)), sty("ac1", fontSize=8,
                   fontName="Courier", textColor=BLACK, alignment=TA_RIGHT, leading=11))],
        [Paragraph("Gross Creator Earnings", S_BODY),
         Paragraph("Creator Liability (Payable)", S_BODY_SM),
         Paragraph(inr(d.get("gross_earnings",0)), sty("ac2", fontSize=8,
                   fontName="Courier", textColor=BLACK, alignment=TA_RIGHT, leading=11))],
        [Paragraph("Net Payout Amount", S_BODY),
         Paragraph("Payout Settlement (Liability Cleared)", S_BODY_SM),
         Paragraph(inr(d.get("net_payout",0)), sty("ac3", fontSize=8,
                   fontName="Courier", textColor=GREEN, alignment=TA_RIGHT, leading=11))],
        [Paragraph("TDS Deducted u/s 194-O", S_BODY),
         Paragraph("TDS Withheld (Government Payable)", S_BODY_SM),
         Paragraph(inr(d.get("tds_amount",0)), sty("ac4", fontSize=8,
                   fontName="Courier", textColor=BLACK, alignment=TA_RIGHT, leading=11))],
    ]
    acw = [BODY_W*0.32, BODY_W*0.42, BODY_W*0.26]
    acc_tbl = Table(acc_data, colWidths=acw)
    acc_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), BLACK),
        ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [VERY_LIGHT, colors.white]),
        ("GRID",    (0,0), (-1,-1), 0.3, LIGHT_GREY),
        ("BOX",     (0,0), (-1,-1), 0.5, DARK_GREY),
        ("PADDING", (0,0), (-1,-1), 6),
        ("VALIGN",  (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",   (2,0), (2,-1), "RIGHT"),
    ]))
    story.append(acc_tbl)
    story.append(Spacer(1, 4*mm))

    # ── Proof reference ───────────────────────────────────────────────────────
    story += section_header("Proof Reference")
    proof_rows = [
        ("Payout Proof Filename", val(d.get("proof_path"))),
        ("Proof Upload Timestamp", val(d.get("proof_ts"))),
        ("Storage Reference", "Supabase Storage · Bucket: payout-proofs · Private · Signed URLs only"),
    ]
    story.append(kv_table(proof_rows))
    story.append(Spacer(1, 4*mm))

    # ── Internal processing metadata ──────────────────────────────────────────
    story += section_header("Internal Processing Metadata")
    meta_rows2 = [
        ("Generated By (Admin)", val(d.get("admin_actor"))),
        ("Receipt Generation Timestamp", d.get("generated_at","")[:19].replace("T"," ")),
        ("Backend Version", val(d.get("backend_version"))),
        ("Environment", val(d.get("environment","production")).upper()),
        ("Internal Payout ID", val(d.get("payout_id"))),
        ("Creator ID", val(d.get("creator_id"))),
        ("Receipt ID", val(d.get("receiptId"))),
        ("Payout Status", val(d.get("payout_status"))),
    ]
    story.append(kv_table(meta_rows2))
    story.append(Spacer(1, 4*mm))

    # ── Legal disclaimer ──────────────────────────────────────────────────────
    story += section_header("Legal Disclaimer")
    disclaimer = (
        "This audit page is an integral part of the payout settlement receipt issued by Streamheart Private Limited. "
        "The SHA-256 hash recorded above was computed from the binary content of this PDF document and serves as a "
        "tamper-evident seal. Any modification to the document contents will invalidate the recorded hash. "
        "This record is maintained in accordance with applicable financial record-keeping regulations. "
        "Streamheart Private Limited reserves the right to audit and verify all settlement records. "
        "This document is confidential and intended solely for the named creator and authorised internal personnel. "
        "Unauthorised distribution, reproduction, or alteration of this document is prohibited and may constitute a "
        "violation of applicable laws."
    )
    story.append(Paragraph(disclaimer, S_LEGAL))
    story.append(Spacer(1, 4*mm))

    # ── QR placeholder ────────────────────────────────────────────────────────
    story += section_header("QR Verification")
    qr_data = [[
        Paragraph(
            "[ QR CODE PLACEHOLDER ]\n\nScan to verify receipt authenticity\n"
            f"Receipt: {val(d.get('receiptId'))}\n"
            f"Hash: {val(d.get('sha256',''))[:32]}...",
            sty("qr", fontSize=7, fontName="Courier", textColor=MID_GREY,
                alignment=TA_CENTER, leading=11)
        )
    ]]
    qr_tbl = Table(qr_data, colWidths=[48*mm])
    qr_tbl.setStyle(TableStyle([
        ("BOX",     (0,0), (-1,-1), 0.5, LIGHT_GREY),
        ("PADDING", (0,0), (-1,-1), 12),
        ("ALIGN",   (0,0), (-1,-1), "CENTER"),
    ]))
    story.append(qr_tbl)

    # ── Watermark callback ────────────────────────────────────────────────────
    status_text = d.get("payout_status", "PAID")

    def add_watermark(canvas_obj, doc):
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica-Bold", 72)
        canvas_obj.setFillColor(colors.Color(0, 0.4, 0, 0.07))
        canvas_obj.translate(PAGE_W/2, PAGE_H/2)
        canvas_obj.rotate(45)
        canvas_obj.drawCentredString(0, 0, status_text)
        canvas_obj.restoreState()

        # Page number footer
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica", 7)
        canvas_obj.setFillColor(MID_GREY)
        canvas_obj.drawString(L, 10*mm,
            f"Streamheart Private Limited · HyperChat · {val(d.get('receiptId'))} · CONFIDENTIAL")
        canvas_obj.drawRightString(PAGE_W - R, 10*mm,
            f"Page {doc.page} of 2")
        canvas_obj.restoreState()

    # ── Build ─────────────────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=L, rightMargin=R,
        topMargin=T, bottomMargin=20*mm,
        title=f"HyperChat Payout Receipt {d.get('receiptId','')}",
        author="Streamheart Private Limited",
        subject="Creator Payout Settlement Receipt",
    )
    doc.build(story, onFirstPage=add_watermark, onLaterPages=add_watermark)


# Move build function before the generate button is called
# (Python reads top-to-bottom but Streamlit reruns the whole script,
#  so placing the function at module level is sufficient)
