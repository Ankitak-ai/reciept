import streamlit as st
import pandas as pd
from utils.supabase_client import supabase
from utils.razorpay_sync import sync_razorpay_payments

st.set_page_config(page_title="Razorpay Payments", page_icon="💳", layout="wide")
st.title("💳 Razorpay Payment Sync & Management")

# ==============================================================================
# 1. SYNC CONTROLS
# ==============================================================================
st.markdown("### 🔄 Sync Controls")
col1, col2 = st.columns([1, 3])

with col1:
    if st.button("🔄 Sync Razorpay Payments", type="primary", use_container_width=True):
        with st.spinner("Fetching payments and matching creators... This may take a moment."):
            metrics, unmapped, errors = sync_razorpay_payments()
            
            if metrics is not None:
                st.session_state["sync_metrics"] = metrics
                st.session_state["unmapped_receipts"] = unmapped
                st.session_state["error_logs"] = errors
                st.success("Sync completed!")
                st.rerun()
            else:
                st.error("Sync failed. Check your Streamlit Secrets for valid Razorpay credentials.")

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

    # Show Unmapped Receipts Details
    if st.session_state.get("unmapped_receipts"):
        with st.expander(f"⚠️ View {len(st.session_state['unmapped_receipts'])} Unmapped Receipts"):
            st.dataframe(
                pd.DataFrame(st.session_state["unmapped_receipts"]), 
                use_container_width=True, 
                hide_index=True
            )
            st.info("💡 Tip: Ensure the creator's `creator_code` matches the prefix of the Razorpay receipt (e.g., receipt 'mc_rp_123' requires creator_code 'mc').")
            
    # Show Error Logs Details
    if st.session_state.get("error_logs"):
        with st.expander(f"❌ View {len(st.session_state['error_logs'])} Error Logs"):
            for err in st.session_state["error_logs"]:
                st.text(err)

# ==============================================================================
# 3. PAYMENT VIEWER (DATAFRAME)
# ==============================================================================
st.markdown("---")
st.markdown("### 📜 Recent Payments")

# Fetch recent payments
res = supabase.table('payments').select(
    'payment_id, order_id, amount, fee, tax, status, method, email, created_at, creator_id'
).order('created_at', desc=True).limit(100).execute()

if not res.data:
    st.info("📭 No payments synced yet. Click the 'Sync Razorpay Payments' button above to fetch data.")
else:
    df = pd.DataFrame(res.data)
    
    # Format amounts from paise to Rupees safely
    def format_inr(val):
        if val is None:
            return "N/A"
        try:
            return f"₹{float(val)/100:.2f}"
        except (ValueError, TypeError):
            return "N/A"

    df['amount'] = df['amount'].apply(format_inr)
    df['fee'] = df['fee'].apply(format_inr)
    df['tax'] = df['tax'].apply(format_inr)
    
    # Fetch creator handles for better readability in the table
    creator_ids = df['creator_id'].dropna().unique().tolist()
    if creator_ids:
        creators_res = supabase.table('creators').select('id, creator_handle').in_('id', creator_ids).execute()
        creator_map = {c['id']: c['creator_handle'] for c in creators_res.data}
        df['creator'] = df['creator_id'].map(creator_map).fillna('Unmapped')
    else:
        df['creator'] = 'Unmapped'

    # Reorder and clean columns for display
    display_cols = ['created_at', 'payment_id', 'creator', 'amount', 'fee', 'tax', 'status', 'method', 'email']
    # Ensure all columns exist before selecting (handles cases where fee/tax might be missing in old schemas)
    safe_display_cols = [col for col in display_cols if col in df.columns]
    
    # Rename created_at for better UI
    df_display = df[safe_display_cols].rename(columns={'created_at': 'Timestamp'})
    
    st.dataframe(
        df_display, 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "Timestamp": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY HH:mm"),
            "status": st.column_config.TextColumn("Status"),
            "amount": st.column_config.TextColumn("Amount"),
        }
    )

    # ==============================================================================
    # 4. RAW PAYLOAD INSPECTOR
    # ==============================================================================
    st.markdown("---")
    st.markdown("### 🔍 Raw Payload Inspector")
    st.caption("Inspect the exact JSON responses returned by the Razorpay API for debugging and auditing.")
    
    # Create a readable list for the selectbox
    payment_options = [f"{row['payment_id']} | {row['creator']} | {row['amount']}" for _, row in df.iterrows()]
    
    selected_payment_str = st.selectbox(
        "Select a payment to inspect raw JSON payloads",
        options=payment_options,
        index=0
    )
    
    if selected_payment_str:
        # Extract the actual payment_id from the formatted string
        selected_payment_id = selected_payment_str.split(" | ")[0]
        
        # Fetch raw payloads for the selected payment
        raw_res = supabase.table('payments').select(
            'raw_payment_payload, raw_order_payload'
        ).eq('payment_id', selected_payment_id).single().execute()
        
        raw_data = raw_res.data
        
        col_a, col_b = st.columns(2)
        
        with col_a:
            st.markdown("**📦 Raw Payment Payload**")
            if raw_data and raw_data.get('raw_payment_payload'):
                st.json(raw_data.get('raw_payment_payload'), expanded=False)
            else:
                st.warning("No raw payment payload found.")
                
        with col_b:
            st.markdown("**📦 Raw Order Payload**")
            if raw_data and raw_data.get('raw_order_payload'):
                st.json(raw_data.get('raw_order_payload'), expanded=False)
            else:
                st.info("No order payload found. This typically happens with Wallet/UPI payments that do not generate a distinct Razorpay Order ID.")
