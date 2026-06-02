import streamlit as st
import pandas as pd
from utils.supabase_client import supabase
from utils.auth import require_auth
from utils.validators import validate_pan

# 🔒 Require authentication for this page
require_auth()

st.set_page_config(page_title="Creator Details", page_icon="👤", layout="wide")
st.title("👤 Creator Details")

if 'selected_creator_id' not in st.session_state:
    st.warning("Please select a creator from the Creator List.")
    st.stop()

creator_id = st.session_state['selected_creator_id']
edit_mode = st.session_state.get('edit_mode', False)

# 1. Fetch Core Profile Data
creator = supabase.table('creators').select('*').eq('id', creator_id).execute().data[0]
financial = supabase.table('creator_financial_info').select('*').eq('creator_id', creator_id).execute()
fin_data = financial.data[0] if financial.data else {}

# 2. Fetch LIFETIME AGGREGATES for accurate Summary Metrics
all_payments = supabase.table('payments').select('amount_inr, fee_inr, tax_inr').eq('creator_id', creator_id).execute().data or []
all_refunds = supabase.table('refunds').select('amount_inr').eq('creator_id', creator_id).execute().data or []

total_gross = sum(p.get('amount_inr', 0) or 0 for p in all_payments)
total_fees = sum(p.get('fee_inr', 0) or 0 for p in all_payments)
total_tax = sum(p.get('tax_inr', 0) or 0 for p in all_payments)
total_refunded = sum(r.get('amount_inr', 0) or 0 for r in all_refunds)

# 3. Fetch LEDGER DATA (Last 50 only) for the UI tables
payments_res = supabase.table('payments').select(
    'payment_id, order_id, amount_inr, fee_inr, tax_inr, status, method, created_at, original_currency, original_amount'
).eq('creator_id', creator_id).order('created_at', desc=True).limit(50).execute()

refunds_res = supabase.table('refunds').select(
    'refund_id, amount_inr, status, created_at, payment_id'
).eq('creator_id', creator_id).order('created_at', desc=True).limit(50).execute()

st.subheader(f"{creator['creator_handle']} ({creator['status']})")

def format_inr(val):
    if val is None: return "0.00"
    try: return f"₹{float(val)/100:.2f}"
    except (ValueError, TypeError): return "₹0.00"

# ==============================================================================
# VIEW MODE (Tabs)
# ==============================================================================
if not edit_mode:
    tab_profile, tab_ledger = st.tabs(["👤 Profile & Financials", "💳 Payments & Refunds"])
    
    # --- TAB 1: PROFILE ---
    with tab_profile:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### Basic Info")
            st.write(f"**Code:** {creator['creator_code']}")
            st.write(f"**Payout Rate:** {creator.get('payout_rate', '89')}%")
            st.write(f"**Email:** {creator.get('email') or 'N/A'}")
            st.write(f"**Phone:** {creator.get('phone_number') or 'N/A'}")
            st.write(f"**Notes:** {creator.get('notes') or 'N/A'}")
        with col2:
            st.markdown("### Financial Info")
            st.write(f"**Legal Name:** {fin_data.get('legal_name') or 'N/A'}")
            st.write(f"**PAN:** {fin_data.get('pan_number') or 'N/A'}")
            st.write(f"**UPI:** {fin_data.get('upi_id') or 'N/A'}")
            st.write(f"**Bank:** {fin_data.get('bank_name') or 'N/A'}")
            st.write(f"**Account (Last 4):** {fin_data.get('account_last4') or 'N/A'}")
            st.write(f"**IFSC:** {fin_data.get('ifsc') or 'N/A'}")

        if st.button("✏️ Edit Profile"):
            st.session_state['edit_mode'] = True
            st.rerun()

    # --- TAB 2: PAYMENTS & REFUNDS ---
    with tab_ledger:
        # Calculate derived metrics based on LIFETIME totals (Gross-Based Model)
        adjusted_gross = total_gross - total_refunded
        payout_rate = float(creator.get('payout_rate', 89))
        creator_share = round(adjusted_gross * (payout_rate / 100))
        platform_commission = adjusted_gross - creator_share
        platform_net_profit = platform_commission - total_fees - total_tax
        
        st.markdown("### 📊 Lifetime Financial Summary")
        m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns(6)
        m_col1.metric("Gross Amount", format_inr(total_gross))
        m_col2.metric("Refunds", format_inr(total_refunded), delta_color="inverse")
        m_col3.metric("Adj. Gross", format_inr(adjusted_gross), help="Gross - Refunds")
        m_col4.metric("Creator Share", format_inr(creator_share), help=f"Adj. Gross × {payout_rate}%")
        m_col5.metric("Platform Comm.", format_inr(platform_commission), help=f"Adj. Gross × {100 - payout_rate}%")
        m_col6.metric("Platform Net Profit", format_inr(platform_net_profit), help="Platform Comm. - Razorpay Fees/Tax")

        st.divider()

        # 1. Payments Dataframe
        st.markdown("### 💸 Recent Payments (Last 50)")
        payments_data = payments_res.data or []
        if not payments_data:
            st.info("No payments found for this creator yet.")
        else:
            df_payments = pd.DataFrame(payments_data)
            df_payments['Gross (INR)'] = df_payments['amount_inr'].apply(format_inr)
            df_payments['Fees (INR)'] = df_payments['fee_inr'].apply(format_inr)
            
            display_payments = df_payments[['created_at', 'payment_id', 'original_currency', 'Gross (INR)', 'Fees (INR)', 'method', 'status']]
            display_payments = display_payments.rename(columns={'created_at': 'Date'})
            
            st.dataframe(display_payments, width="stretch", hide_index=True, column_config={"Date": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY HH:mm")})

        st.divider()

        # 2. Refunds Dataframe
        st.markdown("### ↩️ Recent Refunds (Last 50)")
        refunds_data = refunds_res.data or []
        if not refunds_data:
            st.info("No refunds found for this creator. (This is good!)")
        else:
            df_refunds = pd.DataFrame(refunds_data)
            df_refunds['Deducted (INR)'] = df_refunds['amount_inr'].apply(format_inr)
            display_refunds = df_refunds[['created_at', 'refund_id', 'payment_id', 'Deducted (INR)', 'status']].rename(columns={'created_at': 'Date'})
            st.dataframe(display_refunds, width="stretch", hide_index=True, column_config={"Date": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY HH:mm")})

# ==============================================================================
# EDIT MODE
# ==============================================================================
else:
    st.markdown("### ✏️ Edit Creator Profile & Financials")
    
    def safe_str(val):
        return str(val) if val is not None else ''

    with st.form("edit_form"):
        c_email = st.text_input("Email", value=safe_str(creator.get('email')))
        c_phone = st.text_input("Phone", value=safe_str(creator.get('phone_number')))
        c_notes = st.text_area("Notes", value=safe_str(creator.get('notes')))
        c_payout_rate = st.number_input("Payout Rate (%)", min_value=0.0, max_value=100.0, value=float(creator.get('payout_rate', 89.0)), step=1.0)
        current_status = creator.get('status', 'ACTIVE')
        c_status = st.selectbox("Status", ["ACTIVE", "INACTIVE", "BLOCKED"], index=["ACTIVE", "INACTIVE", "BLOCKED"].index(current_status))
        
        st.markdown("### Financial Info")
        f_legal = st.text_input("Legal Name", value=safe_str(fin_data.get('legal_name')))
        f_pan = st.text_input("PAN", value=str(fin_data.get('pan_number') or '').upper())
        f_upi = st.text_input("UPI ID", value=safe_str(fin_data.get('upi_id')))
        f_bank = st.text_input("Bank Name", value=safe_str(fin_data.get('bank_name')))
        f_holder = st.text_input("Account Holder", value=safe_str(fin_data.get('account_holder_name')))
        f_acc = st.text_input("Acc Last 4", value=safe_str(fin_data.get('account_last4')))
        f_ifsc = st.text_input("IFSC", value=safe_str(fin_data.get('ifsc')))
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            submitted = st.form_submit_button("💾 Save Changes", type="primary", use_container_width=True)
        with col_btn2:
            st.write("")
            st.write("")
            cancel_btn = st.form_submit_button("❌ Cancel", use_container_width=True)
            
        if submitted:
            if f_pan and not validate_pan(f_pan):
                st.error("Invalid PAN format. Must be 5 letters, 4 numbers, 1 letter.")
            else:
                # Helper to convert empty strings to None (prevents DB errors)
                def clean(val):
                    return val if val else None

                try:
                    # 1. Update Core Creator Data
                    supabase.table('creators').update({
                        "email": c_email, 
                        "phone_number": c_phone, 
                        "notes": c_notes, 
                        "status": c_status,
                        "payout_rate": c_payout_rate
                    }).eq('id', creator_id).execute()
                    
                    # 2. Upsert Financial Info (Creates row if missing, updates if exists)
                    supabase.table('creator_financial_info').upsert({
                        "creator_id": creator_id,
                        "legal_name": clean(f_legal), 
                        "pan_number": clean(f_pan), 
                        "upi_id": clean(f_upi),
                        "bank_name": clean(f_bank), 
                        "account_holder_name": clean(f_holder),
                        "account_last4": clean(f_acc),  # ✅ FIXED: Correct column name
                        "ifsc": clean(f_ifsc)
                    }, on_conflict='creator_id').execute()
                        
                    st.success("✅ Updated successfully!")
                    st.session_state['edit_mode'] = False
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to update: {e}")
                    
        elif cancel_btn:
            st.session_state['edit_mode'] = False
            st.rerun()
