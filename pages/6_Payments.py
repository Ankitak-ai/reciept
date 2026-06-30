import streamlit as st
import pandas as pd
import requests
import time
import datetime
from zoneinfo import ZoneInfo
from utils.supabase_client import supabase
from utils.auth import require_auth
from utils.helpers import format_inr

require_auth()

st.set_page_config(page_title="Razorpay Payments", page_icon="💳", layout="wide")
st.title("💳 Razorpay Payment Sync & Management")

IST = ZoneInfo("Asia/Kolkata")
today_ist = datetime.datetime.now(IST).date()

# ✅ BULLETPROOF IST CONVERTER
def safe_to_ist(dt_val):
    try:
        dt = pd.to_datetime(dt_val, utc=True)
        return dt.tz_convert("Asia/Kolkata").strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return str(dt_val)

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
    last_sync_str = last_sync_dt.astimezone(IST).strftime('%d %b %Y, %I:%M %p IST')

st.caption(f"💡 **Smart Sync:** Database is up to date as of **{last_sync_str}**. Clicking sync will only fetch *new* data.")

col1, col2 = st.columns(2)

with col1:
    if st.button("🔄 Sync New & Missing Data", type="primary", use_container_width=True):
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
        st.session_state['last_sync_result'] = {"message": msg, "time": datetime.datetime.now(IST).strftime("%I:%M %p IST")}
        if total_synced > 0: st.balloons()
        st.rerun()

with col2:
    if st.button("🔗 Auto-Remap Unmapped Payments", type="secondary", use_container_width=True):
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
                        "time": datetime.datetime.now(IST).strftime("%I:%M %p IST")
                    }
                    st.balloons()
                    st.rerun()
                else:
                    st.error(f"Auto-remap failed: {response.text}")
            except Exception as e:
                st.error(f"Connection failed: {e}")

st.divider()

# ==============================================================================
# 2. GLOBAL PAYMENTS LEDGER (UI Table Only)
# ==============================================================================
st.markdown("### 📜 Global Payments Ledger")
st.caption("Showing the last 100 payments across all creators for quick viewing.")

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
    
    def format_original(row):
        if row.get('original_currency') and row['original_currency'] != 'INR':
            original_amt = (row['original_amount'] or 0) / 100
            return f"{row['original_currency']} {original_amt:.2f}"
        return ''
    
    df_payments['Original'] = df_payments.apply(format_original, axis=1)
    df_payments['Gross (INR)'] = df_payments['amount_inr'].apply(format_inr)
    df_payments['Fees (INR)'] = df_payments['fee_inr'].apply(format_inr)
    df_payments['Date (IST)'] = df_payments['created_at'].apply(safe_to_ist)
    
    display_cols = ['Date (IST)', 'payment_id', 'Creator', 'Code', 'Original', 'Gross (INR)', 'Fees (INR)', 'method', 'status']
    
    st.dataframe(df_payments[display_cols], width="stretch", hide_index=True)

# ==============================================================================
# 3. TRUE 30-DAY FINANCIAL METRICS (MATCHES RAZORPAY EXACTLY)
# ==============================================================================
st.divider()
st.markdown("### 📊 True Financial Metrics (Last 30 Days)")
st.caption("This exactly matches Razorpay's 'Amount Collected' logic: (Captured Payments) - (Refunds).")

# Calculate exactly 30 days ago in ISO format
thirty_days_ago = (datetime.datetime.now(IST) - datetime.timedelta(days=30)).isoformat()

# 1. Fetch ALL captured payments from the last 30 days (Bypassing the 100 row limit!)
captured_res = supabase.table('payments').select('amount_inr').eq('status', 'captured').gte('created_at', thirty_days_ago).execute()
total_captured_30d = sum(p.get('amount_inr', 0) or 0 for p in (captured_res.data or []))

# 2. Fetch ALL refunds from the last 30 days
refunds_res = supabase.table('refunds').select('amount_inr').gte('created_at', thirty_days_ago).execute()
total_refunds_30d = sum(r.get('amount_inr', 0) or 0 for r in (refunds_res.data or []))

# 3. Calculate TRUE Net Collected
true_net_collected = total_captured_30d - total_refunds_30d

m1, m2, m3 = st.columns(3)
m1.metric("💰 True Collected (Last 30 Days)", format_inr(true_net_collected))
m2.metric("✅ Total Captured (Last 30 Days)", format_inr(total_captured_30d))
m3.metric("↩️ Total Refunds (Last 30 Days)", format_inr(total_refunds_30d), delta_color="inverse")

# ==============================================================================
# 4. UNMAPPED PAYMENTS DEBUG TABLE
# ==============================================================================
st.divider()
st.markdown("### 🔗 Unmapped Payments & Missing Creator Codes")

unmapped_res = supabase.table('payments').select(
    'payment_id, amount_inr, created_at, receipt, creator_code_attempted'
).is_('creator_id', 'null').order('created_at', desc=True).execute()

unmapped_data = unmapped_res.data if (unmapped_res and unmapped_res.data) else []

if not unmapped_data:
    st.success("🎉 **Perfect!** All payments in the database are successfully mapped to creators!")
else:
    st.warning(f"⚠️ There are currently **{len(unmapped_data)}** unmapped payments.")
    
    df_unmapped = pd.DataFrame(unmapped_data)
    df_unmapped['Date (IST)'] = df_unmapped['created_at'].apply(safe_to_ist)
    df_unmapped['Amount (INR)'] = df_unmapped['amount_inr'].apply(format_inr)
    
    df_unmapped = df_unmapped.rename(columns={
        'creator_code_attempted': 'Attempted Creator Code',
        'receipt': 'Raw Razorpay Receipt'
    })
    
    display_unmapped = df_unmapped[['Date (IST)', 'Amount (INR)', 'Attempted Creator Code', 'Raw Razorpay Receipt', 'payment_id']]
    
    st.dataframe(display_unmapped, width="stretch", hide_index=True, column_config={
        "Date (IST)": st.column_config.TextColumn("Date (IST)", width="small"),
        "Amount (INR)": st.column_config.TextColumn("Amount", width="small"),
        "Attempted Creator Code": st.column_config.TextColumn("Missing Code", width="medium"),
        "Raw Razorpay Receipt": st.column_config.TextColumn("Raw Receipt", width="large"),
        "payment_id": st.column_config.TextColumn("Payment ID", width="medium")
    })
