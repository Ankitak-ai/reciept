import streamlit as st
import pandas as pd
import plotly.express as px
from collections import Counter
from utils.supabase_client import supabase
from utils.auth import require_auth
from utils.helpers import format_inr

require_auth()

st.set_page_config(page_title="Master Reconciliation", page_icon="📊", layout="wide")
st.title("📊 Master Ledger & Reconciliation")
st.caption("A complete, all-time breakdown of your actual Razorpay earnings, fees, and payment methods from your Clean Ledger.")

with st.spinner("Aggregating all-time ledger data..."):
    # Fetch all payments
    payments_res = supabase.table('payments').select('amount_inr, fee_inr, tax_inr, status, method, original_currency, original_amount').execute()
    payments = payments_res.data or []
    
    # Fetch all refunds
    refunds_res = supabase.table('refunds').select('amount_inr').execute()
    refunds = refunds_res.data or []

if not payments:
    st.warning("No payments found in the database. Run a Deep Sync first!")
    st.stop()

# Separate by status
captured = [p for p in payments if p.get('status') == 'captured']
failed = [p for p in payments if p.get('status') == 'failed']
refunded_status = [p for p in payments if p.get('status') == 'refunded']

# Financials (Captured only)
gross_captured = sum(p.get('amount_inr', 0) for p in captured)
total_fees = sum(p.get('fee_inr', 0) for p in captured)
total_gst = sum(p.get('tax_inr', 0) for p in captured)
total_fees_and_gst = total_fees + total_gst
net_earnings = gross_captured - total_fees_and_gst
amount_refunded = sum(r.get('amount_inr', 0) for r in refunds)

# Methods & Currencies
methods = Counter(p.get('method', 'unknown') for p in captured)
currencies = Counter(p.get('original_currency', 'INR') for p in captured)

# ==========================================
# UI METRICS
# ==========================================
st.markdown("### 💰 Financial Summary (Actual Money Received)")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Gross Captured", format_inr(gross_captured))
c2.metric("Razorpay Fees", format_inr(total_fees))
c3.metric("GST Component", format_inr(total_gst))
c4.metric("Net Earnings", format_inr(net_earnings))
c5.metric("Amount Refunded", format_inr(amount_refunded), delta_color="inverse" if amount_refunded > 0 else "off")

st.divider()

st.markdown("### 📈 Ledger Breakdown")
col_stat1, col_stat2 = st.columns(2)

with col_stat1:
    st.markdown("#### ── By Status ──")
    status_data = {
        "Status": ["captured", "failed", "refunded"],
        "Count": [len(captured), len(failed), len(refunded_status)]
    }
    st.dataframe(pd.DataFrame(status_data), hide_index=True, width="stretch")
    
    st.markdown("#### ── By Payment Method ──")
    method_df = pd.DataFrame(list(methods.items()), columns=["Method", "Count"]).sort_values("Count", ascending=False)
    st.dataframe(method_df, hide_index=True, width="stretch")

with col_stat2:
    st.markdown("#### ── By Currency ──")
    curr_df = pd.DataFrame(list(currencies.items()), columns=["Currency", "Count"]).sort_values("Count", ascending=False)
    st.dataframe(curr_df, hide_index=True, width="stretch")
    
    # Pie chart for methods
    if sum(methods.values()) > 0:
        fig = px.pie(names=list(methods.keys()), values=list(methods.values()), title="Payment Methods Distribution", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)

st.divider()
st.info("💡 **Why don't I see the 183 'failed' payments here?** Earlier, to protect your Payout Generator from accidentally paying creators for failed bank attempts, we configured your Edge Function to **ignore** failed payments and we deleted the old ones from the database. Your database now acts as a pure 'Clean Ledger' of actual money received. If you want to track failed attempts to monitor your Failure Rate, let me know and we can add a `failed_attempts` table!")
