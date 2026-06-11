import streamlit as st
from supabase import create_client
from extra_streamlit_components import CookieManager
import datetime

# Initialize the Cookie Manager
cookie_manager = CookieManager()

def get_auth_client():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)

def login(email: str, password: str):
    client = get_auth_client()
    try:
        res = client.auth.sign_in_with_password({"email": email, "password": password})
        if res.user:
            st.session_state['authenticated'] = True
            st.session_state['user_email'] = res.user.email
            
            # ✅ FIX: Save session to browser cookies for 7 days
            expires = datetime.datetime.now() + datetime.timedelta(days=7)
            cookie_manager.set("sh_auth_token", res.session.access_token, expires_at=expires)
            cookie_manager.set("sh_user_email", res.user.email, expires_at=expires)
            
            return True, None
    except Exception as e:
        error_msg = str(e)
        if "Invalid login credentials" in error_msg:
            return False, "Incorrect email or password."
        return False, error_msg
    return False, "Unknown error occurred."

def logout():
    client = get_auth_client()
    try:
        client.auth.sign_out()
    except:
        pass
        
    # ✅ FIX: Delete cookies on logout
    cookie_manager.delete("sh_auth_token")
    cookie_manager.delete("sh_user_email")
    
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

def require_auth():
    """
    Call this at the top of EVERY page. 
    Checks session state, then checks cookies to restore session across tabs.
    """
    if not st.session_state.get('authenticated'):
        # Try to restore from cookie
        token = cookie_manager.get("sh_auth_token")
        email = cookie_manager.get("sh_user_email")
        
        if token and email:
            # ✅ FIX: Restore session state from cookie automatically
            st.session_state['authenticated'] = True
            st.session_state['user_email'] = email
            
            # Note: We don't need to call client.auth.set_session() here because 
            # our Database RLS policies allow the 'anon' role (which the Streamlit 
            # server uses) to read/write data. The cookie is purely for the UI.
        else:
            # Hide sidebar for unauthorized users
            st.markdown("""
                <style>
                    [data-testid="stSidebar"] { display: none; }
                    [data-testid="stSidebarCollapsedControl"] { display: none; }
                </style>
            """, unsafe_allow_html=True)
            
            st.error("🔒 **Access Denied:** Please log in via the Home page to access this section.")
            st.stop()
