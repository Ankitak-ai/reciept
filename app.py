import streamlit as st
from utils.auth import login, logout

st.set_page_config(page_title="Login - Creator Management", page_icon="🔒", layout="centered")

# 1. DEBUG MODE: If you add ?debug=true to your URL, it forces a logout
if st.query_params.get("debug") == "true":
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# 2. CHECK AUTHENTICATION
is_authenticated = st.session_state.get('authenticated', False)

if is_authenticated:
    # ==========================================
    # LOGGED IN STATE
    # ==========================================
    st.title("🎬 Creator Management System")
    st.success(f"✅ Logged in as **{st.session_state.get('user_email', 'Admin')}**")
    
    st.markdown("---")
    st.markdown("### 🚀 Use the sidebar to navigate to Payouts, Creators, or Payments.")
        
    if st.button("🚪 Log Out", type="primary", use_container_width=True):
        logout()

else:
    # ==========================================
    # LOGIN STATE (THIS IS WHAT YOU WANT TO SEE)
    # ==========================================
    st.title("🔒 Admin Login")
    st.caption("Please enter your credentials to access the internal dashboard.")

    with st.form("login_form"):
        email = st.text_input("Email Address", placeholder="admin@yourcompany.com")
        password = st.text_input("Password", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("🔓 Log In", type="primary", use_container_width=True)
        
        if submitted:
            if not email or not password:
                st.error("Please enter both email and password.")
            else:
                with st.spinner("Authenticating..."):
                    success, error_msg = login(email, password)
                    if success:
                        st.success("Login successful! Redirecting...")
                        st.rerun()
                    else:
                        st.error(f"❌ {error_msg}")
                        
    st.divider()
    st.caption("Trouble logging in? [Click here to reset session](?debug=true)")
