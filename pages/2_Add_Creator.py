import streamlit as st
from utils.supabase_client import supabase
from utils.validators import validate_pan

st.set_page_config(page_title="Add Creator", page_icon="➕")
st.title("➕ Add New Creator")

with st.form("add_creator_form"):
    st.subheader("Basic Information")
    c_code = st.text_input("Creator Code*", placeholder="e.g., CR001")
    c_handle = st.text_input("Creator Handle*", placeholder="e.g., @creatorname")
    c_email = st.text_input("Email")
    c_phone = st.text_input("Phone Number")
    c_notes = st.text_area("Notes")

    st.subheader("Financial Information")
    f_legal = st.text_input("Legal Name")
    f_pan = st.text_input("PAN Number").upper()
    f_upi = st.text_input("UPI ID")
    f_bank = st.text_input("Bank Name")
    f_holder = st.text_input("Account Holder Name")
    f_acc_last4 = st.text_input("Account Number (Last 4)")
    f_ifsc = st.text_input("IFSC Code")
    
    submitted = st.form_submit_button("Create Creator")

    if submitted:
        if not c_code or not c_handle:
            st.error("Creator Code and Handle are required.")
        elif not validate_pan(f_pan):
            st.error("Invalid PAN format. Must be 5 letters, 4 numbers, 1 letter (e.g., ABCDE1234F).")
        else:
            # Check duplicates
            check_code = supabase.table('creators').select('id').eq('creator_code', c_code).execute()
            check_handle = supabase.table('creators').select('id').eq('creator_handle', c_handle).execute()
            
            if check_code.data or check_handle.data:
                st.error("Creator Code or Handle already exists.")
            else:
                # Insert Creator
                creator_data = {
                    "creator_code": c_code, "creator_handle": c_handle, 
                    "email": c_email, "phone_number": c_phone, "notes": c_notes
                }
                creator_res = supabase.table('creators').insert(creator_data).execute()
                creator_id = creator_res.data[0]['id']

                # Insert Financial Info
                fin_data = {
                    "creator_id": creator_id, "legal_name": f_legal, "pan_number": f_pan,
                    "upi_id": f_upi, "bank_name": f_bank, "account_holder_name": f_holder,
                    "account_number_last4": f_acc_last4, "ifsc": f_ifsc
                }
                supabase.table('creator_financial_info').insert(fin_data).execute()
                
                st.success(f"Creator {c_handle} created successfully!")
                st.balloons()
