import streamlit as st
from supabase import create_client, Client

def get_supabase_client() -> Client:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
        return create_client(url, key)
    except KeyError:
        st.error("⚠️ Missing Supabase credentials in Streamlit secrets. Please check `.streamlit/secrets.toml` or your Streamlit Cloud dashboard.")
        st.stop()

# Initialize globally for easy importing
supabase = get_supabase_client()
