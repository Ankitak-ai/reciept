import streamlit as st
from utils.supabase_client import supabase

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
st.title("📊 Dashboard")

# Fetch counts
res = supabase.table('creators').select('status').execute()
creators = res.data

active = sum(1 for c in creators if c['status'] == 'ACTIVE')
inactive = sum(1 for c in creators if c['status'] == 'INACTIVE')
blocked = sum(1 for c in creators if c['status'] == 'BLOCKED')
total = len(creators)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Creators", total)
col2.metric("Active", active)
col3.metric("Inactive", inactive)
col4.metric("Blocked", blocked)
