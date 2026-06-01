import streamlit as st
from utils.supabase_client import supabase

from utils.auth import require_auth
require_auth()

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
st.title("📊 Dashboard")

res = supabase.table('creators').select('status').execute()
creators = res.data

active = sum(1 for c in creators if c['status'] == 'ACTIVE')
inactive = sum(1 for c in creators if c['status'] == 'INACTIVE')
blocked = sum(1 for c in creators if c['status'] == 'BLOCKED')

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Creators", len(creators))
col2.metric("Active", active)
col3.metric("Inactive", inactive)
col4.metric("Blocked", blocked)
