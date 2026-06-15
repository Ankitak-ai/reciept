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
# 1. SYNC CONTROLS (SMART ORCHESTRATOR)
# ==============================================================================
st.markdown("### 🔄 Sync Controls")
st.caption("Clicking this will automatically download your entire Razorpay history in chunks. No limits, no local scripts required.")

if st.button("🔄 Sync ALL Historical Data", type="primary", width="stretch"):
    function_url = st.secrets.get("BACKFILL_URL")
    secret_token = st.secrets.get("BACKFILL_SECRET")
    anon_key = st.secrets.get("SUPABASE_ANON_KEY")
    
    if not function_url or not secret_token or not anon_key:
        st.error("Missing BACKFILL_URL, BACKFILL_SECRET, or SUPABASE_ANON_KEY in Streamlit secrets.")
        st.stop()
        
    headers = {
        "Authorization": f"Bearer {anon_key}",
        "x-backfill-secret": secret_token,
        "Content-Type": "application/json"
    }
    
    skip = 0
    batch_size = 500
    total_synced = 0
    total_refunds = 0
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    while True:
        status_text.info(f"⏳ **Working...** Fetching batch starting at record **{skip}**. Total synced so far: **{total_synced}**")
        
        payload = {"skip": skip, "limit": batch_size}
        
        try:
            response = requests.post(function_url, headers=headers, json=payload, timeout=90)
            
            if response.status_code == 200:
                result = response.json()
                synced_this_batch = result.get("payments_synced", 0)
                refunds_this_batch = result.get("refunds_synced", 0)
                
                total_synced += synced_this_batch
                total_refunds += refunds_this_batch
                
                if synced_this_batch == 0:
                    break # Reached the absolute end of Razorpay history
                    
                skip += batch_size
            else:
                st.error(f"Server error at record {skip}: {response.text}")
                break
                
        except Exception as e:
            st.error(f"Connection failed at record {skip}: {e}")
            break
            
    progress_bar.progress(100)
    st.success(f"🎉 **Complete!** Successfully synced **{total_synced} payments** and **{total_refunds} refunds** to the CMS database.")
    st.balloons()
    time.sleep(2)
    st.rerun()

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
    unmapped_count = len([p for p in payments_data if not p.get('creator_id')])
    
    st.divider()
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Gross (Last 100)", format_inr(total_gross))
    m2.metric("Total Razorpay Fees", format_inr(total_fees))
    m3.metric("Unmapped Payments", unmapped_count, help="Payments where the creator code was missing or invalid.")

st.divider()

# ==============================================================================
# 3. BULK REMAP TOOL
# ==============================================================================
st.markdown("### 🔗 Bulk Remap Unmapped Payments")
st.caption("Use this to assign historical payments to a creator that was added AFTER the payments were received.")

unmapped_count_res = supabase.table('payments').select('id', count='exact').is_('creator_id', 'null').execute()
total_unmapped = unmapped_count_res.count if (unmapped_count_res and unmapped_count_res.count is not None) else 0

if total_unmapped > 0:
    st.info(f"There are currently **{total_unmapped}** unmapped payments in the database.")
    
    with st.form("bulk_remap_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            remap_start = st.date_input("Start Date", value=today_ist - datetime.timedelta(days=30))
        with c2:
            remap_end = st.date_input("End Date", value=today_ist)
        with c3:
            creators_res = supabase.table('creators').select('id, creator_handle, creator_code').eq('status', 'ACTIVE').order('creator_handle').execute()
            creators_list = creators_res.data if (creators_res and creators_res.data) else []
            creator_options = {f"{c['creator_handle']} ({c['creator_code']})": c['id'] for c in creators_list}
            
            if not creator_options:
                st.warning("No active creators found.")
                selected_creator_id = None
            else:
                selected_creator_label = st.selectbox("Assign to Creator", options=list(creator_options.keys()))
                selected_creator_id = creator_options[selected_creator_label]
                
        submitted_remap = st.form_submit_button("🔗 Map Unmapped Payments", type="primary", width="stretch")
        
        if submitted_remap and selected_creator_id:
            start_dt = datetime.datetime.combine(remap_start, datetime.time.min, tzinfo=IST)
            end_dt = datetime.datetime.combine(remap_end, datetime.time.max, tzinfo=IST)
            start_iso = start_dt.astimezone(datetime.timezone.utc).isoformat()
            end_iso = end_dt.astimezone(datetime.timezone.utc).isoformat()
            
            try:
                res = supabase.table('payments').update({"creator_id": selected_creator_id})\
                    .is_('creator_id', 'null')\
                    .gte('created_at', start_iso)\
                    .lte('created_at', end_iso)\
                    .execute()
                
                updated_count = len(res.data) if (res and res.data) else 0
                st.success(f"✅ Successfully mapped {updated_count} payments to {selected_creator_label}!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Failed to remap: {e}")
else:
    st.success("🎉 All payments in the database are successfully mapped to creators!")
