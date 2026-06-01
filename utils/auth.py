# utils/auth.py
import streamlit as st
from supabase import create_client

def get_auth_client():
    """Initializes Supabase client using the ANON key for secure auth."""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)

def login(email: str, password: str):
    """Attempts to log the user in and sets session state."""
    client = get_auth_client()
    try:
        res = client.auth.sign_in_with_password({"email": email, "password": password})
        if res.user:
            st.session_state['authenticated'] = True
            st.session_state['user_email'] = res.user.email
            return True, None
    except Exception as e:
        error_msg = str(e)
        if "Invalid login credentials" in error_msg:
            return False, "Incorrect email or password."
        return False, error_msg
    return False, "Unknown error occurred."

def logout():
    """Clears session state and logs the user out."""
    client = get_auth_client()
    client.auth.sign_out()
    # Clear all streamlit session state
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

def require_auth():
    """
    Call this at the top of EVERY page to ensure the user is logged in.
    If not, it stops the page from rendering.
    """
    if not st.session_state.get('authenticated'):
        st.error("🔒 **Access Denied:** Please log in via the Home page to access this section.")
        st.stop()
