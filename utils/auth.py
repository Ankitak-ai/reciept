import streamlit as st
from supabase import create_client
from streamlit_js_eval import get_cookie, set_cookie

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
            
            # ✅ Save session to browser cookies for 7 days
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
        
    # ✅ FIX: Expire cookies immediately (-1 days) to delete them from the browser
    set_cookie('sh_auth_token', '', -1)
    set_cookie('sh_user_email', '', -1)
    
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

def require_auth():
    """
    Call this at the top of EVERY page. 
    Uses JS to fetch cookies without deadlocking the Streamlit render tree.
    """
    if not st.session_state.get('authenticated'):
        # Use singular get_cookie()
        token = get_cookie('sh_auth_token')
        email = get_cookie('sh_user_email')
        
        if token and email:
            # ✅ Restore session state from cookie automatically
            st.session_state['authenticated'] = True
            st.session_state['user_email'] = email
            st.rerun() # Rerun to apply the session state to the page
            
        elif token is None and email is None:
            # 🔄 DEADLOCK PREVENTION: 
            # On the very first millisecond of a page load, JS hasn't evaluated yet, 
            # so it returns None. We MUST let the script finish rendering so the 
            # hidden JS component can execute in the browser and trigger a rerun.
            st.info("🔄 Restoring your session...")
            # DO NOT use st.stop() here!
            
        else:
            # JS has evaluated, and the cookies are genuinely empty/missing -> User is logged out
            st.markdown("""
                <style>
                    [data-testid="stSidebar"] { display: none; }
                    [data-testid="stSidebarCollapsedControl"] { display: none; }
                </style>
            """, unsafe_allow_html=True)
            
            st.error("🔒 **Access Denied:** Please log in via the Home page to access this section.")
            st.stop()
