import streamlit as st
import pandas as pd
import plotly.express as px
from utils.supabase_client import supabase
from utils.auth import require_auth
from utils.helpers import format_inr

require_auth()

st.set_page_config(page_title="Platform Financials", page_icon="📊", layout="wide")
st.title("📊 StreamHeart Financials & Balance Sheet")
st.caption("Consolidated Profit & Loss, Liabilities, and Cash Flow for StreamHeart Private Limited.")

# Fetch Data
with st.spinner("Aggregating financial data across all tables..."):
    payments_res = supabase.table('payments').select('amount_inr, fee_inr, tax_inr').execute()
    refunds_res = supabase.table('refunds').select('amount_inr').execute()
    payouts_res = supabase.table('payouts').select('creator_share_inr, platform_commission_inr, status').execute()

payments = payments_res.data or []
refunds = refunds_res.data or []
payouts = payouts_res.data or []

# ==============================================================================
# CORE ACCOUNTING CALCULATIONS
# ==============================================================================
total_gmv = sum(p.get('amount_inr', 0) or 0 for p in payments)
total_refunds = sum(r.get('amount_inr', 0) or 0 for r in refunds)
total_gateway_fees = sum((p.get('fee_inr', 0) or 0) + (p.get('tax_inr', 0) or 0) for p in payments)

total_creator_payouts_generated = sum(p.get('creator_share_inr', 0) or 0 for p in payouts)
total_platform_commission = sum(p.get('platform_commission_inr', 0) or 0 for p in payouts)

net_revenue = total_gmv - total_refunds
net_profit = total_platform_commission - total_gateway_fees

# Balance Sheet Metrics
accounts_payable = sum(p.get('creator_share_inr', 0) or 0 for p in payouts if p.get('status') == 'PENDING')
cash_disbursed = sum(p.get('creator_share_inr', 0) or 0 for p in payouts if p.get('status') == 'PAID')

# ==============================================================================
# TABS
# ==============================================================================
tab_pl, tab_bs, tab_export = st.tabs(["📈 Profit & Loss (Income Statement)", "⚖️ Balance Sheet (Liabilities)", "⬇️ CA Export"])

# --- TAB 1: P&L ---
with tab_pl:
    st.markdown("### 📈 Profit & Loss Statement")
    st.info("This represents the operational performance of StreamHeart Private Limited.")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Gross Transaction Value (GMV)", format_inr(total_gmv))
    col2.metric("Less: Refunds", format_inr(total_refunds), delta_color="inverse")
    col3.metric("Net Revenue", format_inr(net_revenue))
    
    st.divider()
    
    col4, col5 = st.columns(2)
    col4.metric("Gross Profit (Platform Commission)", format_inr(total_platform_commission), help="Total 11% / 10% cut retained by platform")
    col5.metric("Less: Gateway Fees (Razorpay + GST)", format_inr(total_gateway_fees), delta_color="inverse", help="Absorbed by the platform")
    
    st.divider()
    
    st.metric("🔥 Net Profit (Bottom Line)", format_inr(net_profit), help="Gross Profit - Gateway Fees", delta_color="normal")
    
    # Visualization
    if total_creator_payouts_generated > 0 or total_platform_commission > 0:
        fig = px.pie(
            names=["Creator Payouts (Liability)", "Platform Commission (Revenue)"],
            values=[total_creator_payouts_generated, total_platform_commission],
            title="Revenue Distribution (GMV Split)",
            hole=0.4,
            color_discrete_sequence=px.colors.sequential.Blues_r
        )
        st.plotly_chart(fig, use_container_width=True)

# --- TAB 2: BALANCE SHEET ---
with tab_bs:
    st.markdown("### ⚖️ Balance Sheet (Snapshot)")
    st.info("Current liabilities represent money collected from viewers but not yet disbursed to creators.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📉 Current Liabilities")
        st.metric("Accounts Payable (Pending Payouts)", format_inr(accounts_payable), help="Money owed to creators for generated but unpaid payouts.")
        st.caption("These are unsettled liabilities on StreamHeart's books. They must be cleared by marking payouts as PAID.")
        
    with col2:
        st.markdown("#### 💸 Cash Flow (Outflows)")
        st.metric("Cash Disbursed (Paid Payouts)", format_inr(cash_disbursed), help="Money successfully transferred to creators.")
        st.metric("Gateway Fees Paid to Razorpay", format_inr(total_gateway_fees), help="Cash outflow to payment processors.")
        
    st.divider()
    st.markdown("#### 📊 Payout Status Ledger")
    
    if payouts:
        df_payouts = pd.DataFrame(payouts)
        status_counts = df_payouts['status'].value_counts().reset_index()
        status_counts.columns = ['Status', 'Count']
        st.dataframe(status_counts, use_container_width=True, hide_index=True)
    else:
        st.info("No payouts generated yet.")

# --- TAB 3: CA EXPORT ---
with tab_export:
    st.markdown("### ⬇️ Export for Chartered Accountant (CA)")
    st.caption("Download the raw aggregated financial data for tax filing, GST reconciliation, and audit purposes.")
    
    export_data = {
        "Financial Metric": [
            "Gross Transaction Value (GMV)",
            "Total Refunds Processed",
            "Net Revenue",
            "Total Creator Payouts Generated",
            "Platform Gross Profit (Commission)",
            "Payment Gateway Fees (Razorpay + GST)",
            "Platform Net Profit",
            "Accounts Payable (Pending Payouts)",
            "Cash Disbursed to Creators"
        ],
        "Amount (INR)": [
            total_gmv / 100,
            total_refunds / 100,
            net_revenue / 100,
            total_creator_payouts_generated / 100,
            total_platform_commission / 100,
            total_gateway_fees / 100,
            net_profit / 100,
            accounts_payable / 100,
            cash_disbursed / 100
        ]
    }
    
    df_export = pd.DataFrame(export_data)
    st.dataframe(df_export, use_container_width=True, hide_index=True)
    
    csv = df_export.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Financial Summary (CSV)",
        data=csv,
        file_name="streamheart_financial_summary.csv",
        mime="text/csv",
        use_container_width=True
    )
