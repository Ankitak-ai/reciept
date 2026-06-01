import streamlit as st
import pandas as pd
from utils.supabase_client import supabase

# Import the sync function (ensure it's in utils or defined above)
# from utils.razorpay_sync import sync_razorpay_payments 

st.set_page_config(page_title="Razorpay Payments", page_icon="💳", layout="wide")
st.title("💳 Razorpay Payment Sync & Management")

# ================= SYNC CONTROLS =================
st.markdown("### 🔄 Sync Controls")
col1, col2 = st.columns([1, 3])

with col1:
    if st.button("🔄 Sync Razorpay Payments", type="primary", use_container_width=True):
        with st.spinner("Fetching payments and matching creators..."):
            # Call the sync function defined in Step 3
            metrics, unmapped, errors = sync_razorpay_payments()
            
            if metrics:
                st.session_state["sync_metrics"] = metrics
                st.session_state["unmapped"] = unmapped
                st.session_state["errors"] = errors
                st.rerun()

# ================= SYNC SUMMARY =================
if "sync_metrics" in st.session_state:
    m = st.session_state["sync_metrics"]
    st.markdown("### 📊 Sync Summary")
    cols = st.columns(5)
    cols[0].metric("Fetched", m["fetched"])
    cols[1].metric("Inserted", m["inserted"], delta_color="normal")
    cols[2].metric("Duplicates", m["duplicate"], delta_color="inverse")
    cols[3].metric("Unmapped", m["unmapped"], delta_color="inverse")
    cols[4].metric("Errors", m["errors"], delta_color="inverse")

    if st.session_state.get("unmapped"):
        with st.expander("⚠️ View Unmapped Receipts"):
            st.json(st.session_state["unmapped"])
            
    if st.session_state.get("errors"):
        with st.expander("❌ View Error Logs"):
            for err in st.session_state["errors"]:
                st.error(err)

# ================= PAYMENT VIEWER =================
st.markdown("### 📜 Recent Payments")
res = supabase.table('payments').select(
    'payment_id, order_id, amount, fee, tax, status, method, email, created_at, creator_id'
).order('created_at', desc=True).limit(50).execute()

if not res.data:
    st.info("No payments synced yet.")
else:
    df = pd.DataFrame(res.data)
    
    # Format amounts from paise to rupees
    df['amount'] = df['amount'].apply(lambda x: f"₹{x/100:.2f}" if x else "N/A")
    df['fee'] = df['fee'].apply(lambda x: f"₹{x/100:.2f}" if x else "N/A")
    
    # Fetch creator handles for display
    creator_ids = df['creator_id'].dropna().unique().tolist()
    if creator_ids:
        creators_res = supabase.table('creators').select('id, creator_handle').in_('id', creator_ids).execute()
        creator_map = {c['id']: c['creator_handle'] for c in creators_res.data}
        df['creator_handle'] = df['creator_id'].map(creator_map).fillna('Unmapped')
    
    # Drop raw payloads and internal IDs from main view
    display_df = df[['created_at', 'payment_id', 'creator_handle', 'amount', 'fee', 'status', 'method', 'email']]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ================= RAW PAYLOAD VIEWER =================
    st.markdown("### 🔍 Raw Payload Inspector")
    selected_payment = st.selectbox(
        "Select a payment to inspect raw JSON payloads",
        options=[f"{row['payment_id']} ({row['creator_handle']})" for _, row in df.iterrows()],
        index=0
    )
    
    if selected_payment:
        pid = selected_payment.split(" ")[0]
        raw_res = supabase.table('payments').select('raw_payment_payload, raw_order_payload').eq('payment_id', pid).single().execute()
        raw_data = raw_res.data
        
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Raw Payment Payload**")
            st.json(raw_data.get('raw_payment_payload'))
        with col_b:
            st.markdown("**Raw Order Payload**")
            if raw_data.get('raw_order_payload'):
                st.json(raw_data.get('raw_order_payload'))
            else:
                st.info("No order payload found (Payment may be wallet/UPI without order ID).")
