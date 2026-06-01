import streamlit as st
from utils.supabase_client import supabase
from utils.validators import validate_pan

st.set_page_config(page_title="Creator Details", page_icon="👤", layout="wide")
st.title("👤 Creator Details")

if 'selected_creator_id' not in st.session_state:
    st.warning("Please select a creator from the Creator List.")
    st.stop()

creator_id = st.session_state['selected_creator_id']
edit_mode = st.session_state.get('edit_mode', False)

# Fetch Data
creator = supabase.table('creators').select('*').eq('id', creator_id).execute().data[0]
financial = supabase.table('creator_financial_info').select('*').eq('creator_id', creator_id).execute()
fin_data = financial.data[0] if financial.data else {}

st.subheader(f"{creator['creator_handle']} ({creator['status']})")

# ================= VIEW MODE =================
if not edit_mode:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Basic Info")
        st.write(f"**Code:** {creator['creator_code']}")
        # Using 'or' to handle None values from the database
        st.write(f"**Email:** {creator['email'] or 'N/A'}")
        st.write(f"**Phone:** {creator['phone_number'] or 'N/A'}")
        st.write(f"**Notes:** {creator['notes'] or 'N/A'}")
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

# ================= EDIT MODE =================
else:
    st.markdown("### ✏️ Edit Creator")
    with st.form("edit_form"):
        # Added 'or ""' to prevent NoneType errors in text inputs
        c_email = st.text_input("Email", value=creator['email'] or '')
        c_phone = st.text_input("Phone", value=creator['phone_number'] or '')
        c_notes = st.text_area("Notes", value=creator['notes'] or '')
        c_status = st.selectbox("Status", ["ACTIVE", "INACTIVE", "BLOCKED"], index=["ACTIVE", "INACTIVE", "BLOCKED"].index(creator['status']))
        
        st.markdown("### Financial Info")
        f_legal = st.text_input("Legal Name", value=fin_data.get('legal_name') or '')
        # THIS WAS THE CRASH POINT: Added 'or ""' before .upper()
        f_pan = st.text_input("PAN", value=fin_data.get('pan_number') or '').upper()
        f_upi = st.text_input("UPI ID", value=fin_data.get('upi_id') or '')
        f_bank = st.text_input("Bank Name", value=fin_data.get('bank_name') or '')
        f_holder = st.text_input("Account Holder", value=fin_data.get('account_holder_name') or '')
        f_acc = st.text_input("Acc Last 4", value=fin_data.get('account_number_last4') or '')
        f_ifsc = st.text_input("IFSC", value=fin_data.get('ifsc') or '')
        
        submitted = st.form_submit_button("Save Changes")
        
        if submitted:
            if f_pan and not validate_pan(f_pan):
                st.error("Invalid PAN format. Must be 5 letters, 4 numbers, 1 letter.")
            else:
                supabase.table('creators').update({
                    "email": c_email, "phone_number": c_phone, 
                    "notes": c_notes, "status": c_status
                }).eq('id', creator_id).execute()
                
                if fin_data:
                    supabase.table('creator_financial_info').update({
                        "legal_name": f_legal, "pan_number": f_pan, "upi_id": f_upi,
                        "bank_name": f_bank, "account_holder_name": f_holder,
                        "account_number_last4": f_acc, "ifsc": f_ifsc
                    }).eq('creator_id', creator_id).execute()
                    
                st.success("Updated successfully!")
                st.session_state['edit_mode'] = False
                st.rerun()
