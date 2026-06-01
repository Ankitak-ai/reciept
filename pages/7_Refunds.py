import streamlit as st
import pandas as pd
import requests
from utils.supabase_client import supabase

st.set_page_config(page_title="Refund Management", page_icon="💸", layout="wide")
st.title("💸 Razorpay Refund Sync & Ledger")

# ⚠️ IMPORTANT: Replace this with your actual Supabase Project URL
EDGE_FUNCTION_URL = "https://ewbaqylcvdmbigtjarow.supabase.co/functions/v1/sync-refunds"

# ==============================================================================
# 1. SYNC CONTROLS (Triggering the Edge Function)
# ==============================================================================
st.markdown("### 🔄 Sync Controls")
st.info("💡 Syncing refunds ensures that chargebacks and refunded donations are accurately deducted from creator payouts.")

col1, col2 = st.columns([1, 3])

with col1:
    if st.button("🔄 Sync Refunds from Razorpay", type="primary", width="stretch"):
        with st.spinner("Fetching refunds and mapping to creators..."):
            try:
                # Pass the Supabase Service Role Key to bypass the Edge Gateway JWT requirement
                supabase_key = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
                headers = {
                    "Authorization": f"Bearer {supabase_key}",
                    "Content-Type": "application/json"
                }
                
                # Call the Edge Function (Timeout set to 3 minutes)
                response = requests.post(EDGE_FUNCTION_URL, headers=headers, timeout=180)
                
                # Check HTTP status BEFORE trying to parse JSON
                if response.status_code != 200:
                    st.error(f"❌ Edge Function returned HTTP {response.status_code}")
                    with st.expander("🔍 Debug: Raw Edge Function Response"):
                        st.code(response.text)
                    st.stop()

                # Parse the JSON response from Deno
                result = response.json()
                
                if result.get("success"):
                    st.session_state["refund_sync_metrics"] = result["metrics"]
                    st.success("✅ Refund sync completed successfully!")
                    st.rerun()
                else:
                    st.error(f"❌ Sync failed: {result.get('error', 'Unknown error')}")
                    with st.expander("🔍 Debug: Raw Edge Function Response"):
                        st.code(str(result))
                        
            except requests.exceptions.Timeout:
                st.error("⏱️ Sync timed out. Check Supabase Edge Function logs.")
            except Exception as e:
                st.error(f"❌ Failed to connect to Edge Function: {str(e)}")

# ==============================================================================
# 2. SYNC SUMMARY METRICS
# ==============================================================================
if "refund_sync_metrics" in st.session_state:
    st.markdown("---")
    st.markdown("### 📊 Last Sync Summary")
    m = st.session_state["refund_sync_metrics"]
    
    cols = st.columns(4)
    cols[0].metric("Fetched", m.get("fetched", 0))
    cols[1].metric("Inserted", m.get("inserted", 0), delta_color="normal")
    cols[2].metric("Duplicates Skipped", m.get("duplicate", 0), delta_color="inverse")
    cols[3].metric("Unmapped (No Creator)", m.get("unmapped", 0), delta_color="inverse")

# ==============================================================================
# 3. REFUNDS LEDGER (Dataframe)
# ==============================================================================
st.markdown("---")
st.markdown("### 📜 Refund Ledger")
st.caption("Refunds are automatically deducted from the respective creator's net payout during settlement generation.")

# Fetch refunds with a left join to get the creator handle
res = supabase.table('refunds').select(
    'refund_id, status, amount, amount_inr, created_at, creator:creator_id(creator_handle)'
).order('created_at', desc=True).limit(100).execute()

if not res.data:
    st.info("📭 No refunds synced yet. Click the 'Sync Refunds' button above to fetch data.")
else:
    df = pd.DataFrame(res.data)
    
    # Format amounts from paise to Rupees safely
    def format_inr(val):
        if val is None: return "N/A"
        try: return f"₹{float(val)/100:.2f}"
        except (ValueError, TypeError): return "N/A"

    # Apply formatting
    df['Original Amount (Subunits)'] = df['amount']
    df['Deducted (INR ₹)'] = df['amount_inr'].apply(format_inr)
    
    # Extract creator handle from the nested JSON object returned by Supabase join
    df['Creator'] = df['creator'].apply(lambda x: x['creator_handle'] if x and isinstance(x, dict) else 'Unmapped/External')
    
    # Clean up columns for display
    df_display = df[['created_at', 'refund_id', 'Creator', 'status', 'Original Amount (Subunits)', 'Deducted (INR ₹)']]
    df_display = df_display.rename(columns={'created_at': 'Refund Date'})
    
    st.dataframe(
        df_display, 
        width="stretch", 
        hide_index=True,
        column_config={
            "Refund Date": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY HH:mm"),
            "status": st.column_config.TextColumn("Status"),
            "Deducted (INR ₹)": st.column_config.TextColumn("INR Deduction", help="The exact amount deducted from the creator's payout in INR."),
        }
    )
    
    # Quick summary of total financial impact
    total_deducted_paise = df['amount_inr'].sum()
    total_refunds_count = len(df)
    
    st.markdown(f"**Total Financial Impact of Visible Refunds:** 📉 **{format_inr(total_deducted_paise)}** deducted across **{total_refunds_count}** transactions.")
