import streamlit as st
import pandas as pd
from utils.supabase_client import supabase
from utils.validators import validate_pan

st.set_page_config(page_title="Creator Details", page_icon="👤", layout="wide")
st.title("👤 Creator Details")

if 'selected_creator_id' not in st.session_state:
    st.warning("Please select a creator from the Creator List.")
    st.stop()

creator_id = st.session_state['selected_creator_id']
edit_mode = st.session_state.get('edit_mode', False)

# Fetch Core Data
creator = supabase.table('creators').select('*').eq('id', creator_id).execute().data[0]
financial = supabase.table('creator_financial_info').select('*').eq('creator_id', creator_id).execute()
fin_data = financial.data[0] if financial.data else {}

# Fetch Financial Ledger Data for Tab 2
payments_res = supabase.table('payments').select(
    'payment_id, order_id, amount_inr, fee_inr, tax_inr, status, method, created_at, original_currency, original_amount'
).eq('creator_id', creator_id).order('created_at', desc=True).limit(50).execute()

refunds_res = supabase.table('refunds').select(
    'refund_id, amount_inr, status, created_at, payment_id'
).eq('creator_id', creator_id).order('created_at', desc=True).limit(50).execute()

st.subheader(f"{creator['creator_handle']} ({creator['status']})")

# Helper for currency formatting
def format_inr(val):
    if val is None: return "₹0.00"
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
            st.write(f"**Account (Last 4):** {fin_data.get('account_number_last4') or 'N/A'}")
            st.write(f"**IFSC:** {fin_data.get('ifsc') or 'N/A'}")

        if st.button("Back to List"):
            st.session_state['edit_mode'] = False
            st.switch_page("pages/3_Creator_List.py")

    # --- TAB 2: PAYMENTS & REFUNDS ---
    with tab_ledger:
        # 1. Calculate Summary Metrics
        payments_data = payments_res.data or []
        refunds_data = refunds_res.data or []
        
        total_gross = sum(p.get('amount_inr', 0) or 0 for p in payments_data)
        total_fees = sum(p.get('fee_inr', 0) or 0 for p in payments_data)
        total_tax = sum(p.get('tax_inr', 0) or 0 for p in payments_data)
        total_refunded = sum(r.get('amount_inr', 0) or 0 for r in refunds_data)
        
        net_base = total_gross - total_fees - total_tax
        final_net = net_base - total_refunded
        
        st.markdown("### 📊 Financial Summary (Last 50 Transactions)")
        m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
        m_col1.metric("Gross Amount", format_inr(total_gross))
        m_col2.metric("Razorpay Fees", format_inr(total_fees), delta_color="inverse")
        m_col3.metric("Refunds", format_inr(total_refunded), delta_color="inverse")
        m_col4.metric("Net Base", format_inr(net_base))
        m_col5.metric("Creator Share (Est)", format_inr(final_net * (float(creator.get('payout_rate', 89)) / 100)), help=f"Calculated at {creator.get('payout_rate', 89)}% payout rate")

        st.divider()

        # 2. Payments Dataframe
        st.markdown("### 💸 Recent Payments")
        if not payments_data:
            st.info("No payments found for this creator yet.")
        else:
            df_payments = pd.DataFrame(payments_data)
            df_payments['Gross (INR)'] = df_payments['amount_inr'].apply(format_inr)
            df_payments['Fees (INR)'] = df_payments['fee_inr'].apply(format_inr)
            df_payments['Net (INR)'] = (df_payments['amount_inr'].fillna(0) - df_payments['fee_inr'].fillna(0) - df_payments['tax_inr'].fillna(0)).apply(format_inr)
            
            display_payments = df_payments[['created_at', 'payment_id', 'original_currency', 'Gross (INR)', 'Fees (INR)', 'Net (INR)', 'method', 'status']]
            display_payments = display_payments.rename(columns={'created_at': 'Date'})
            
            st.dataframe(
                display_payments, 
                width="stretch", 
                hide_index=True,
                column_config={
                    "Date": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY HH:mm"),
                    "original_currency": st.column_config.TextColumn("Curr", help="Original Currency"),
                }
            )

        st.divider()

        # 3. Refunds Dataframe
        st.markdown("### ↩️ Recent Refunds")
        if not refunds_data:
            st.info("No refunds found for this creator. (This is good!)")
        else:
            df_refunds = pd.DataFrame(refunds_data)
            df_refunds['Deducted (INR)'] = df_refunds['amount_inr'].apply(format_inr)
            
            display_refunds = df_refunds[['created_at', 'refund_id', 'payment_id', 'Deducted (INR)', 'status']]
            display_refunds = display_refunds.rename(columns={'created_at': 'Date'})
            
            st.dataframe(
                display_refunds, 
                width="stretch", 
                hide_index=True,
                column_config={
                    "Date": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY HH:mm"),
                }
            )

# ==============================================================================
# EDIT MODE (Unchanged, just renders the form directly)
# ==============================================================================
else:
    st.markdown("### ✏️ Edit Creator")
    
    def safe_str(val):
        return str(val) if val is not None else ''

    with st.form("edit_form"):
        c_email = st.text_input("Email", value=safe_str(creator.get('email')))
        c_phone = st.text_input("Phone", value=safe_str(creator.get('phone_number')))
        c_notes = st.text_area("Notes", value=safe_str(creator.get('notes')))
        
        # Added Payout Rate to the edit form!
        c_payout_rate = st.number_input(
            "Payout Rate (%)", 
            min_value=0.0, 
            max_value=100.0, 
            value=float(creator.get('payout_rate', 89.0)), 
            step=1.0,
            help="The percentage of the net payout this creator receives."
        )
        
        current_status = creator.get('status', 'ACTIVE')
        c_status = st.selectbox(
            "Status", 
            ["ACTIVE", "INACTIVE", "BLOCKED"], 
            index=["ACTIVE", "INACTIVE", "BLOCKED"].index(current_status)
        )
        
        st.markdown("### Financial Info")
        f_legal = st.text_input("Legal Name", value=safe_str(fin_data.get('legal_name')))
        pan_val = str(fin_data.get('pan_number') or '')
        f_pan = st.text_input("PAN", value=pan_val.upper())
        f_upi = st.text_input("UPI ID", value=safe_str(fin_data.get('upi_id')))
        f_bank = st.text_input("Bank Name", value=safe_str(fin_data.get('bank_name')))
        f_holder = st.text_input("Account Holder", value=safe_str(fin_data.get('account_holder_name')))
        f_acc = st.text_input("Acc Last 4", value=safe_str(fin_data.get('account_number_last4')))
        f_ifsc = st.text_input("IFSC", value=safe_str(fin_data.get('ifsc')))
        
        submitted = st.form_submit_button("Save Changes", width="stretch")
        
        if submitted:
            if f_pan and not validate_pan(f_pan):
                st.error("Invalid PAN format. Must be 5 letters, 4 numbers, 1 letter (e.g., ABCDE1234F).")
            else:
                supabase.table('creators').update({
                    "email": c_email, 
                    "phone_number": c_phone, 
                    "notes": c_notes, 
                    "status": c_status,
                    "payout_rate": c_payout_rate # Save the new rate!
                }).eq('id', creator_id).execute()
                
                if fin_data:
                    supabase.table('creator_financial_info').update({
                        "legal_name": f_legal, 
                        "pan_number": f_pan, 
                        "upi_id": f_upi,
                        "bank_name": f_bank, 
                        "account_holder_name": f_holder,
                        "account_number_last4": f_acc, 
                        "ifsc": f_ifsc
                    }).eq('creator_id', creator_id).execute()
                    
                st.success("✅ Updated successfully!")
                st.session_state['edit_mode'] = False
                st.rerun()
