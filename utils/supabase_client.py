import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def get_supabase_client() -> Client:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
        return create_client(url, key)
    except KeyError:
        st.error("⚠️ Missing Supabase credentials. Please add them in the Streamlit Cloud Dashboard under Settings > Secrets.")
        st.stop()

supabase = get_supabase_client()
