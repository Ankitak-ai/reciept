import streamlit as st
import pandas as pd
import requests
from utils.supabase_client import supabase

st.set_page_config(page_title="Razorpay Payments", page_icon="💳", layout="wide")
st.title("💳 Razorpay Payment Sync & Management")

# Get your Edge Function URL from the Supabase Dashboard
EDGE_FUNCTION_URL = "https://ewbaqylcvdmbigtjarow.supabase.co/functions/v1/sync-razorpay"

# ==============================================================================
# 1. SYNC CONTROLS (Now just a simple HTTP trigger)
# ==============================================================================
st.markdown("### 🔄 Sync Controls")
col1, col2 = st.columns([1, 3])

with col1:
    if st.button("🔄 Sync Razorpay Payments", type="primary", width="stretch"):
        with st.spinner("Triggering background sync... This may take a minute."):
            try:
                # Call the Edge Function
                response = requests.post(EDGE_FUNCTION_URL, timeout=300) # 5 min timeout
                result = response.json()
                
                if result.get("success"):
                    st.session_state["sync_metrics"] = result["metrics"]
                    st.session_state["unmapped_receipts"] = result.get("unmapped_receipts", [])
                    st.success("Sync completed successfully!")
                    st.rerun()
                else:
                    st.error(f"Sync failed: {result.get('error', 'Unknown error')}")
            except Exception as e:
                st.error(f"Failed to connect to Edge Function: {str(e)}")

# ==============================================================================
# 2. SYNC SUMMARY METRICS
# ==============================================================================
if "sync_metrics" in st.session_state:
    st.markdown("---")
    st.markdown("### 📊 Last Sync Summary")
    m = st.session_state["sync_metrics"]
    
    cols = st.columns(5)
    cols[0].metric("Fetched", m["fetched"])
    cols[1].metric("Inserted", m["inserted"], delta_color="normal")
    cols[2].metric("Duplicates", m["duplicate"], delta_color="inverse")
    cols[3].metric("Unmapped", m["unmapped"], delta_color="inverse")
    cols[4].metric("Errors", m["errors"], delta_color="inverse")

    if st.session_state.get("unmapped_receipts"):
        with st.expander(f"⚠️ View {len(st.session_state['unmapped_receipts'])} Unmapped Receipts"):
            st.dataframe(
                pd.DataFrame(st.session_state["unmapped_receipts"]), 
                width="stretch", hide_index=True
            )

# ==============================================================================
# 3. PAYMENT VIEWER (Dataframe)
# ==============================================================================
st.markdown("---")
st.markdown("### 📜 Recent Payments")

res = supabase.table('payments').select(
    'payment_id, order_id, amount, fee, tax, status, method, email, created_at, creator_id'
).order('created_at', desc=True).limit(100).execute()

if not res.data:
    st.info("📭 No payments synced yet. Click the 'Sync Razorpay Payments' button above.")
else:
    df = pd.DataFrame(res.data)
    
    def format_inr(val):
        if val is None: return "N/A"
        try: return f"₹{float(val)/100:.2f}"
        except (ValueError, TypeError): return "N/A"

    df['amount'] = df['amount'].apply(format_inr)
    df['fee'] = df['fee'].apply(format_inr)
    df['tax'] = df['tax'].apply(format_inr)
    
    creator_ids = df['creator_id'].dropna().unique().tolist()
    if creator_ids:
        creators_res = supabase.table('creators').select('id, creator_handle').in_('id', creator_ids).execute()
        creator_map = {c['id']: c['creator_handle'] for c in creators_res.data}
        df['creator'] = df['creator_id'].map(creator_map).fillna('Unmapped')
    else:
        df['creator'] = 'Unmapped'

    display_cols = ['created_at', 'payment_id', 'creator', 'amount', 'fee', 'tax', 'status', 'method', 'email']
    safe_display_cols = [col for col in display_cols if col in df.columns]
    df_display = df[safe_display_cols].rename(columns={'created_at': 'Timestamp'})
    
    st.dataframe(
        df_display, width="stretch", hide_index=True,
        column_config={
            "Timestamp": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY HH:mm"),
        }
    )
