import streamlit as st
from supabase import create_client
from extra_streamlit_components import CookieManager
import datetime

# ✅ FIX 1: Cache the CookieManager so it only initializes once per server session
@st.cache_resource
def get_cookie_manager():
    return CookieManager()

cookie_manager = get_cookie_manager()

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
            
            # Save session to browser cookies for 7 days
            expires = datetime.datetime.now() + datetime.timedelta(days=7)
            
            # ✅ FIX 2: Added unique keys to prevent Streamlit DuplicateWidgetID error
            cookie_manager.set("sh_auth_token", res.session.access_token, expires_at=expires, key="set_token")
            cookie_manager.set("sh_user_email", res.user.email, expires_at=expires, key="set_email")
            
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
        
    # ✅ FIX 3: Added unique keys for deletion
    cookie_manager.delete("sh_auth_token", key="delete_token")
    cookie_manager.delete("sh_user_email", key="delete_email")
    
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

def require_auth():
    """
    Call this at the top of EVERY page. 
    Checks session state, then checks cookies to restore session across tabs.
    """
    if not st.session_state.get('authenticated'):
        # ✅ FIX 4: Added unique keys for getting cookies
        token = cookie_manager.get("sh_auth_token", key="get_token")
        email = cookie_manager.get("sh_user_email", key="get_email")
        
        if token and email:
            # Restore session state from cookie automatically
            st.session_state['authenticated'] = True
            st.session_state['user_email'] = email
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
