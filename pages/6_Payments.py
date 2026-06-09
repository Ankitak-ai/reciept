import streamlit as st
import pandas as pd
import requests
import base64
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
# 1. MANUAL SYNC FALLBACK
# ==============================================================================
st.markdown("### 🔄 Sync Controls")
st.caption("Webhooks handle real-time syncing automatically. Use this only as a fallback or to backfill historical data.")

col1, col2 = st.columns([1, 3])
with col1:
    if st.button("🔄 Force Manual Sync", type="primary", width="stretch"):
        with st.spinner("Triggering background sync... This may take a minute."):
            try:
                rzp_key_id = st.secrets.get("RAZORPAY_KEY_ID")
                rzp_key_secret = st.secrets.get("RAZORPAY_KEY_SECRET")
                
                if not rzp_key_id or not rzp_key_secret:
                    st.error("Razorpay API keys missing in Streamlit Secrets.")
                    st.stop()
                    
                auth_header = base64.b64encode(f"{rzp_key_id}:{rzp_key_secret}".encode()).decode()
                headers = {"Authorization": f"Basic {auth_header}"}
                
                # Fetch Payments
                url = "https://api.razorpay.com/v1/payments?count=100"
                response = requests.get(url, headers=headers)
                
                json_res = response.json()
                rzp_payments = json_res.get('items', []) if isinstance(json_res, dict) else (json_res if isinstance(json_res, list) else [])
                
                synced_count = 0
                for p in rzp_payments:
                    receipt = ''
                    order_id = p.get('order_id')
                    
                    # ✅ FIX: Razorpay attaches the receipt to the ORDER, not the Payment.
                    if order_id:
                        try:
                            order_url = f"https://api.razorpay.com/v1/orders/{order_id}"
                            order_res = requests.get(order_url, headers=headers)
                            if order_res.status_code == 200:
                                order_data = order_res.json()
                                receipt = order_data.get('receipt', '')
                        except Exception:
                            pass
                            
                    if not receipt:
                        notes = p.get('notes')
                        if isinstance(notes, dict):
                            receipt = notes.get('receipt', '')
                            
                    creator_code = receipt.split('_')[0] if receipt else None
                    
                    creator_id = None
                    if creator_code:
                        try:
                            # ✅ FIX: Use .limit(1) instead of .maybe_single() to prevent NoneType errors
                            creator_res = supabase.table('creators').select('id').eq('creator_code', creator_code).limit(1).execute()
                            if creator_res and creator_res.data and len(creator_res.data) > 0:
                                creator_id = creator_res.data[0]['id']
                        except Exception:
                            pass
                            
                    supabase.table('payments').upsert({
                        "payment_id": p['id'],
                        "order_id": order_id,
                        "amount_inr": p['amount'],
                        "fee_inr": p.get('fee', 0),
                        "tax_inr": p.get('tax', 0),
                        "status": p['status'],
                        "method": p['method'],
                        "original_currency": p['currency'],
                        "original_amount": p['amount'],
                        "creator_id": creator_id,
                        "is_settled": False,
                        "created_at": pd.to_datetime(p['created_at'], unit='s').isoformat()
                    }, on_conflict='payment_id').execute()
                    synced_count += 1
                    
                # Fetch Refunds
                ref_url = "https://api.razorpay.com/v1/refunds?count=100"
                ref_response = requests.get(ref_url, headers=headers)
                
                ref_json = ref_response.json()
                rzp_refunds = ref_json.get('items', []) if isinstance(ref_json, dict) else (ref_json if isinstance(ref_json, list) else [])
                
                for r in rzp_refunds:
                    supabase.table('refunds').upsert({
                        "refund_id": r['id'],
                        "payment_id": r['payment_id'],
                        "amount_inr": r.get('amount', 0),
                        "amount": r.get('amount', 0),
                        "status": r['status'],
                        "created_at": pd.to_datetime(r['created_at'], unit='s').isoformat()
                    }, on_conflict='refund_id').execute()
                    
                st.success(f"✅ Successfully synced {synced_count} payments and {len(rzp_refunds)} refunds!")
                time.sleep(1)
                st.rerun()
                
            except Exception as e:
                st.error(f"Sync failed: {e}")

st.divider()

# ==============================================================================
# 2. GLOBAL PAYMENTS LEDGER
# ==============================================================================
st.markdown("### 📜 Global Payments Ledger")
st.caption("Showing the last 100 successful payments across all creators. (Timestamps are in IST).")

payments_res = supabase.table('payments').select(
    '*, creators:creator_id(creator_handle, creator_code)'
).order('created_at', desc=True).limit(100).execute()

# ✅ FIX: Safely check if res and res.data exist
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
                
                # ✅ FIX: Safely check if res and res.data exist
                updated_count = len(res.data) if (res and res.data) else 0
                st.success(f"✅ Successfully mapped {updated_count} payments to {selected_creator_label}!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Failed to remap: {e}")
else:
    st.success("🎉 All payments in the database are successfully mapped to creators!")
