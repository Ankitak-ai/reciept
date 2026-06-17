import streamlit as st
import pandas as pd
import requests
import time
import datetime
from zoneinfo import ZoneInfo
from utils.supabase_client import supabase
from utils.auth import require_auth
from utils.helpers import format_inr, to_ist

require_auth()

st.set_page_config(page_title="Razorpay Payments", page_icon="💳", layout="wide")
st.title("💳 Razorpay Payment Sync & Management")

IST = ZoneInfo("Asia/Kolkata")
today_ist = datetime.datetime.now(IST).date()

# ==============================================================================
# 1. SYNC CONTROLS
# ==============================================================================
st.markdown("### 🔄 Sync Controls")

if 'last_sync_result' in st.session_state:
    res = st.session_state['last_sync_result']
    st.success(f"🎉 **Last Sync Complete:** {res['message']} (Completed at {res['time']})")
    if st.button("Dismiss", key="dismiss_sync"):
        del st.session_state['last_sync_result']
        st.rerun()

latest_res = supabase.table('payments').select('created_at').order('created_at', desc=True).limit(1).execute()
from_timestamp = 0
last_sync_str = "Beginning of time"

if latest_res.data and len(latest_res.data) > 0:
    last_sync_dt = datetime.datetime.fromisoformat(latest_res.data[0]['created_at'].replace('Z', '+00:00'))
    from_timestamp = int(last_sync_dt.timestamp())
    last_sync_str = last_sync_dt.strftime('%d %b %Y %H:%M IST')

st.caption(f"💡 **Smart Sync:** Database is up to date as of **{last_sync_str}**. Clicking sync will only fetch *new* data.")

col1, col2 = st.columns(2)

with col1:
    if st.button("🔄 Sync New & Missing Data", type="primary", width="stretch"):
        function_url = st.secrets.get("BACKFILL_URL")
        secret_token = st.secrets.get("BACKFILL_SECRET")
        anon_key = st.secrets.get("SUPABASE_ANON_KEY")
        
        if not function_url or not secret_token or not anon_key:
            st.error("Missing secrets.")
            st.stop()
            
        headers = {"Authorization": f"Bearer {anon_key}", "x-backfill-secret": secret_token, "Content-Type": "application/json"}
        
        skip = 0
        batch_size = 500
        total_synced = 0
        total_refunds = 0
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        while True:
            status_text.info(f"⏳ Fetching batch... Total new synced: {total_synced}")
            payload = {"skip": skip, "limit": batch_size, "from_timestamp": from_timestamp}
            
            try:
                response = requests.post(function_url, headers=headers, json=payload, timeout=90)
                if response.status_code == 200:
                    result = response.json()
                    total_synced += result.get("payments_synced", 0)
                    total_refunds += result.get("refunds_synced", 0)
                    if result.get("processed_count", 0) == 0: break
                    skip += batch_size
                else:
                    st.error(f"Server error: {response.text}")
                    break
            except Exception as e:
                st.error(f"Connection failed: {e}")
                break
                
        progress_bar.progress(100)
        msg = f"Synced {total_synced} new payments and {total_refunds} refunds." if total_synced > 0 else "Database is already 100% up to date!"
        st.session_state['last_sync_result'] = {"message": msg, "time": datetime.datetime.now(IST).strftime("%H:%M:%S IST")}
        if total_synced > 0: st.balloons()
        st.rerun()

with col2:
    if st.button("🔗 Auto-Remap Unmapped Payments", type="secondary", width="stretch"):
        function_url = st.secrets.get("BACKFILL_URL").replace('/backfill', '/auto-remap')
        secret_token = st.secrets.get("BACKFILL_SECRET")
        anon_key = st.secrets.get("SUPABASE_ANON_KEY")
        
        headers = {"Authorization": f"Bearer {anon_key}", "x-backfill-secret": secret_token}
        
        with st.spinner("Scanning unmapped payments and fetching Razorpay orders..."):
            try:
                response = requests.post(function_url, headers=headers, timeout=120)
                if response.status_code == 200:
                    result = response.json()
                    st.session_state['last_sync_result'] = {
                        "message": result.get('message', 'Auto-remap complete.'), 
                        "time": datetime.datetime.now(IST).strftime("%H:%M:%S IST")
                    }
                    st.balloons()
                    st.rerun()
                else:
                    st.error(f"Auto-remap failed: {response.text}")
            except Exception as e:
                st.error(f"Connection failed: {e}")

st.divider()

# ==============================================================================
# 2. GLOBAL PAYMENTS LEDGER
# ==============================================================================
st.markdown("### 📜 Global Payments Ledger")
st.caption("Showing the last 100 successful payments across all creators. (Timestamps are in IST).")

payments_res = supabase.table('payments').select(
    '*, creators:creator_id(creator_handle, creator_code)'
).order('created_at', desc=True).limit(100).execute()

payments_data = payments_res.data if (payments_res and payments_res.data) else []

if not payments_data:
    st.info("No payments found in the database yet.")
else:
    df_payments = pd.DataFrame(payments_data)
    
    df_payments['Creator'] = df_payments['creators'].apply(lambda x: x['creator_handle'] if x else 'Unmapped')
    df_payments['Code'] = df_payments['creators'].apply(lambda x: x['creator_code'] if x else '-')
    df_payments['Gross (INR)'] = df_payments['amount_inr'].apply(format_inr)
    df_payments['Fees (INR)'] = df_payments['fee_inr'].apply(format_inr)
    df_payments['Date (IST)'] = df_payments['created_at'].apply(to_ist)
    
    display_cols = ['Date (IST)', 'payment_id', 'Creator', 'Code', 'original_currency', 'Gross (INR)', 'Fees (INR)', 'method', 'status']
    
    st.dataframe(df_payments[display_cols], width="stretch", hide_index=True)
    
    total_gross = sum(p.get('amount_inr', 0) or 0 for p in payments_data)
    total_fees = sum(p.get('fee_inr', 0) or 0 for p in payments_data)

# ==============================================================================
# 3. UNMAPPED PAYMENTS DEBUG TABLE
# ==============================================================================
st.divider()
st.markdown("### 🔗 Unmapped Payments & Missing Creator Codes")
st.caption("If a payment is unmapped, it means the creator code attached to the Razorpay receipt doesn't exist in your CMS yet. Use this table to see exactly which codes you need to add.")

# Fetch unmapped payments with the new debug columns
unmapped_res = supabase.table('payments').select(
    'payment_id, amount_inr, created_at, receipt, creator_code_attempted'
).is_('creator_id', 'null').order('created_at', desc=True).execute()

unmapped_data = unmapped_res.data if (unmapped_res and unmapped_res.data) else []

if not unmapped_data:
    st.success("🎉 **Perfect!** All payments in the database are successfully mapped to creators!")
else:
    st.warning(f"⚠️ There are currently **{len(unmapped_data)}** unmapped payments. See the exact Razorpay codes below:")
    
    df_unmapped = pd.DataFrame(unmapped_data)
    df_unmapped['Date (IST)'] = df_unmapped['created_at'].apply(to_ist)
    df_unmapped['Amount (INR)'] = df_unmapped['amount_inr'].apply(format_inr)
    
    # Rename columns for the UI
    df_unmapped = df_unmapped.rename(columns={
        'creator_code_attempted': 'Attempted Creator Code',
        'receipt': 'Raw Razorpay Receipt'
    })
    
    display_unmapped = df_unmapped[['Date (IST)', 'Amount (INR)', 'Attempted Creator Code', 'Raw Razorpay Receipt', 'payment_id']]
    
    st.dataframe(display_unmapped, width="stretch", hide_index=True, column_config={
        "Date (IST)": st.column_config.TextColumn("Date", width="small"),
        "Amount (INR)": st.column_config.TextColumn("Amount", width="small"),
        "Attempted Creator Code": st.column_config.TextColumn("Missing Code to Add", width="medium"),
        "Raw Razorpay Receipt": st.column_config.TextColumn("Raw Receipt String", width="large"),
        "payment_id": st.column_config.TextColumn("Payment ID", width="medium")
    })
    
    st.info("💡 **Action Required:** Look at the **Attempted Creator Code** column. If you see a code like `xyz`, go to the **Creator List** page and add a new creator with the code `xyz`. Once added, click the **Auto-Remap** button at the top of this page to link these payments instantly!")
