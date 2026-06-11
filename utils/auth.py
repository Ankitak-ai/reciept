import streamlit as st
from supabase import create_client
from streamlit_js_eval import get_cookies, set_cookie, delete_cookie

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
            
            # ✅ Save session to browser cookies for 7 days using JS eval
            set_cookie('sh_auth_token', res.session.access_token, 7)
            set_cookie('sh_user_email', res.user.email, 7)
            
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
        
    # ✅ Delete cookies on logout
    delete_cookie('sh_auth_token')
    delete_cookie('sh_user_email')
    
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

def require_auth():
    """
    Call this at the top of EVERY page. 
    Uses JS to fetch cookies without deadlocking the Streamlit render tree.
    """
    if not st.session_state.get('authenticated'):
        # get_cookies() returns None on the very first millisecond of a page load 
        # before the JavaScript has executed. We must let it load.
        cookies = get_cookies()
        
        if cookies is None:
            # JS hasn't loaded the cookies yet. Show a loading state and let the script finish.
            st.info("🔄 Restoring your session...")
            st.stop()
            
        # JS has loaded. Check if the auth token exists.
        token = cookies.get('sh_auth_token')
        email = cookies.get('sh_user_email')
        
        if token and email:
            # ✅ Restore session state from cookie automatically
            st.session_state['authenticated'] = True
            st.session_state['user_email'] = email
            st.rerun() # Rerun to apply the session state to the page
        else:
            # Cookies loaded, but no token found -> Genuinely logged out
            st.markdown("""
                <style>
                    [data-testid="stSidebar"] { display: none; }
                    [data-testid="stSidebarCollapsedControl"] { display: none; }
                </style>
            """, unsafe_allow_html=True)
            
            st.error("🔒 **Access Denied:** Please log in via the Home page to access this section.")
            st.stop()
