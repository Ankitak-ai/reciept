import streamlit as st
from supabase import create_client, Client

# Fetch secrets using Streamlit's native secrets management
try:
    url: str = st.secrets["SUPABASE_URL"]
    key: str = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
except KeyError:
    st.error("Missing Supabase credentials in Streamlit secrets. Please check your configuration.")
    st.stop()

if not url or not key:
    st.error("Supabase URL or Service Role Key is empty.")
    st.stop()

# Initialize Supabase Client
supabase: Client = create_client(url, key)
