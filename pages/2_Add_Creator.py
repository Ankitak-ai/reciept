import streamlit as st
from utils.supabase_client import supabase
from utils.auth import require_auth
from utils.validators import validate_pan

require_auth()

st.set_page_config(page_title="Add Creator", page_icon="➕", layout="wide")
st.title("➕ Add New Creator")

with st.form("add_creator_form"):
    st.markdown("### Basic Info")
    c1, c2 = st.columns(2)
    with c1:
        handle = st.text_input("Creator Handle / Username *", placeholder="e.g., No Mercy")
        email = st.text_input("Email", placeholder="creator@email.com")
    with c2:
        code = st.text_input("Creator Code (Prefix) *", placeholder="e.g., nm", help="Used for mapping Razorpay payments (e.g., nm_12345)")
        phone = st.text_input("Phone Number")
    
    payout_rate = st.number_input("Payout Rate (%)", min_value=0.0, max_value=100.0, value=89.0, step=1.0)
    notes = st.text_area("Notes")
    
    st.markdown("### Financial Info (Optional for now)")
    f1, f2 = st.columns(2)
    with f1:
        legal_name = st.text_input("Legal Name")
        pan = st.text_input("PAN Number")
        upi = st.text_input("UPI ID")
    with f2:
        bank_name = st.text_input("Bank Name")
        acc_holder = st.text_input("Account Holder Name")
        acc_last4 = st.text_input("Account Number (Last 4 digits)")
        ifsc = st.text_input("IFSC Code")
        
    submitted = st.form_submit_button("✅ Add Creator", type="primary", width="stretch")
    
    if submitted:
        if not handle or not code:
            st.error("Creator Handle and Creator Code are required.")
        elif pan and not validate_pan(pan):
            st.error("Invalid PAN format. Must be 5 letters, 4 numbers, 1 letter.")
        else:
            # Helper to convert empty strings to None (prevents DB constraint errors)
            def clean(val):
                return val if val else None

            try:
                # 1. Insert/Update Core Creator Data
                creator_data = {
                    "creator_handle": handle,
                    "creator_code": code.lower().strip(),
                    "email": clean(email),
                    "phone_number": clean(phone),
                    "payout_rate": payout_rate,
                    "notes": clean(notes),
                    "status": "ACTIVE"
                }
                
                # Use upsert to prevent crashes if creator code already exists
                creator_res = supabase.table('creators').upsert(
                    creator_data, 
                    on_conflict='creator_code'
                ).execute()
                
                creator_id = creator_res.data[0]['id']
                
                # 2. Insert/Update Financial Info
                fin_data = {
                    "creator_id": creator_id,
                    "legal_name": clean(legal_name),
                    "pan_number": clean(pan.upper() if pan else None),
                    "upi_id": clean(upi),
                    "bank_name": clean(bank_name),
                    "account_holder_name": clean(acc_holder),
                    "account_number_last4": clean(acc_last4), # ✅ Exact schema match
                    "ifsc": clean(ifsc)
                }
                
                # ✅ FIX: Use upsert on creator_id to prevent unique constraint violations
                supabase.table('creator_financial_info').upsert(
                    fin_data, 
                    on_conflict='creator_id'
                ).execute()
                
                st.success(f"✅ Successfully added {handle}!")
                st.balloons()
                
            except Exception as e:
                # This will now print the exact Supabase error if something else goes wrong
                st.error(f"Failed to add creator: {e}")
