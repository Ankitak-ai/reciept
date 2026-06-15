import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)

supabase = init_connection()

def fetch_all(query_func):
    """
    Bypasses Supabase's 1,000 row limit by paginating automatically.
    Pass a lambda function that returns the Supabase query builder.
    
    Example:
    payments = fetch_all(lambda: supabase.table('payments').select('*').eq('status', 'captured'))
    """
    all_data = []
    offset = 0
    limit = 1000
    while True:
        # Execute the query with the current range
        res = query_func().range(offset, offset + limit - 1).execute()
        data = res.data or []
        all_data.extend(data)
        
        # If we got less than the limit, we've reached the end of the table
        if len(data) < limit:
            break
        offset += limit
    return all_data
