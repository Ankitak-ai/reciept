import streamlit as st
import pandas as pd
from utils.supabase_client import supabase

st.set_page_config(page_title="Creator List", page_icon="📋")
st.title("📋 Creator List")

# Filters
col1, col2 = st.columns(2)
with col1:
    search_query = st.text_input("Search by Handle or Code")
with col2:
    status_filter = st.selectbox("Filter by Status", ["ALL", "ACTIVE", "INACTIVE", "BLOCKED"])

# Fetch Data
query = supabase.table('creators').select('id, creator_handle, creator_code, email, status, created_at')
if status_filter != "ALL":
    query = query.eq('status', status_filter)

res = query.execute()
creators = res.data

if not creators:
    st.info("No creators found. Try adjusting your filters or add a new creator.")
else:
    df = pd.DataFrame(creators)
    if search_query:
        df = df[df['creator_handle'].str.contains(search_query, case=False, na=False) | 
                df['creator_code'].str.contains(search_query, case=False, na=False)]
    
    if df.empty:
        st.warning("No creators match your search criteria.")
    else:
        # Display actions
        for index, row in df.iterrows():
            cols = st.columns([2, 2, 2, 1, 1, 1])
            cols[0].write(f"**{row['creator_handle']}**")
            cols[1].write(row['creator_code'])
            cols[2].write(row['email'] or "N/A")
            
            if cols[3].button("View", key=f"view_{row['id']}"):
                st.session_state['selected_creator_id'] = row['id']
                st.switch_page("pages/4_Creator_Details.py")
                
            if cols[4].button("Edit", key=f"edit_{row['id']}"):
                st.session_state['selected_creator_id'] = row['id']
                st.session_state['edit_mode'] = True
                st.switch_page("pages/4_Creator_Details.py")
                
            if cols[5].button("Deactivate" if row['status'] == 'ACTIVE' else "Activate", key=f"toggle_{row['id']}"):
                new_status = 'INACTIVE' if row['status'] == 'ACTIVE' else 'ACTIVE'
                supabase.table('creators').update({"status": new_status}).eq('id', row['id']).execute()
                st.rerun()
