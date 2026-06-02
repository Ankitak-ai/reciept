import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
from utils.supabase_client import supabase
from utils.auth import require_auth
from utils.helpers import format_inr

require_auth()

st.set_page_config(page_title="Platform Financials", page_icon="📊", layout="wide")
st.title("📊 StreamHeart Financials & Balance Sheet")
st.caption("Consolidated Profit & Loss, Liabilities, Expenses, and Cash Flow for StreamHeart Private Limited.")

# Fetch Data
with st.spinner("Aggregating financial data..."):
    payments_res = supabase.table('payments').select('amount_inr, fee_inr, tax_inr').execute()
    refunds_res = supabase.table('refunds').select('amount_inr').execute()
    payouts_res = supabase.table('payouts').select('creator_share_inr, platform_commission_inr, status').execute()
    expenses_res = supabase.table('expenses').select('*').order('expense_date', desc=True).execute()

payments = payments_res.data or []
refunds = refunds_res.data or []
payouts = payouts_res.data or []
expenses = expenses_res.data or []

# ==============================================================================
# CORE ACCOUNTING CALCULATIONS
# ==============================================================================
total_gmv = sum(p.get('amount_inr', 0) or 0 for p in payments)
total_refunds = sum(r.get('amount_inr', 0) or 0 for r in refunds)
total_gateway_fees = sum((p.get('fee_inr', 0) or 0) + (p.get('tax_inr', 0) or 0) for p in payments)

total_creator_payouts_generated = sum(p.get('creator_share_inr', 0) or 0 for p in payouts)
total_platform_commission = sum(p.get('platform_commission_inr', 0) or 0 for p in payouts)

net_revenue = total_gmv - total_refunds
operating_profit = total_platform_commission - total_gateway_fees

# Expense Calculations
total_expenses = sum(e.get('amount_inr', 0) or 0 for e in expenses)
final_net_profit = operating_profit - total_expenses

# Balance Sheet Metrics
accounts_payable = sum(p.get('creator_share_inr', 0) or 0 for p in payouts if p.get('status') == 'PENDING')
cash_disbursed = sum(p.get('creator_share_inr', 0) or 0 for p in payouts if p.get('status') == 'PAID')

# ==============================================================================
# TABS
# ==============================================================================
tab_pl, tab_exp, tab_bs, tab_export = st.tabs(["📈 Profit & Loss", "💸 Business Expenses", "⚖️ Balance Sheet", "⬇️ CA Export"])

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
    
    st.metric("Operating Profit (EBITDA)", format_inr(operating_profit), help="Gross Profit - Gateway Fees")
    
    st.divider()
    
    col6, col7 = st.columns(2)
    col6.metric("Less: Manual Business Expenses", format_inr(total_expenses), delta_color="inverse", help="Server, Marketing, Legal, SaaS")
    col7.metric("🔥 Final Net Profit (Bottom Line)", format_inr(final_net_profit), delta_color="normal" if final_net_profit >= 0 else "inverse")
    
    # Visualization
    if total_creator_payouts_generated > 0 or total_platform_commission > 0:
        fig = px.pie(
            names=["Creator Payouts", "Platform Commission", "Gateway Fees", "Business Expenses"],
            values=[total_creator_payouts_generated, total_platform_commission, total_gateway_fees, total_expenses],
            title="Cash Outflow & Revenue Distribution",
            hole=0.4,
            color_discrete_sequence=px.colors.sequential.Blues_r
        )
        st.plotly_chart(fig, width="stretch")

# --- TAB 2: EXPENSES ---
with tab_exp:
    st.markdown("### 💸 Manage Business Expenses")
    st.info("Add manual expenses like server costs, marketing, software subscriptions, legal fees, etc.")
    
    with st.form("add_expense_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            category = st.selectbox("Category", ["Server/Hosting", "Software/SaaS", "Marketing", "Legal/Compliance", "Office/Admin", "Contractor/Freelancer", "Other"])
        with c2:
            amount_rupees = st.number_input("Amount (INR ₹)", min_value=0.0, step=100.0, format="%.2f")
        with c3:
            expense_date = st.date_input("Date", value=datetime.date.today())
            
        description = st.text_input("Description / Notes", placeholder="e.g., AWS Monthly Bill, Supabase Pro Plan, CA Retainer")
        
        submitted = st.form_submit_button("➕ Add Expense", type="primary", width="stretch")
        
        if submitted:
            if amount_rupees <= 0:
                st.error("Amount must be greater than 0.")
            else:
                amount_paise = int(amount_rupees * 100)
                try:
                    supabase.table('expenses').insert({
                        "category": category,
                        "description": description,
                        "amount_inr": amount_paise,
                        "expense_date": expense_date.isoformat()
                    }).execute()
                    st.success("✅ Expense added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to add expense: {e}")
                    
    st.divider()
    st.markdown("#### 📜 Expense Ledger")
    
    if expenses:
        df_exp = pd.DataFrame(expenses)
        df_exp['Amount (₹)'] = df_exp['amount_inr'].apply(lambda x: f"₹{x/100:,.2f}")
        df_exp['Date'] = pd.to_datetime(df_exp['expense_date']).dt.strftime('%d %b %Y')
        
        display_exp = df_exp[['id', 'Date', 'category', 'description', 'Amount (₹)']].rename(columns={
            'category': 'Category',
            'description': 'Description'
        })
        
        st.dataframe(display_exp.drop(columns=['id']), width="stretch", hide_index=True)
        
        st.markdown("##### 🗑️ Remove Incorrect Expense")
        
        exp_options = {
            f"{row['Date']} | {row['Category']} | {row['Amount (₹)']} | {row['Description']}": row['id'] 
            for _, row in display_exp.iterrows()
        }
        
        col_del1, col_del2 = st.columns([3, 1])
        with col_del1:
            selected_exp = st.selectbox("Select expense to delete", options=list(exp_options.keys()))
        with col_del2:
            st.write("")
            st.write("")
            if st.button("Delete", type="secondary", width="stretch"):
                exp_id = exp_options[selected_exp]
                supabase.table('expenses').delete().eq('id', exp_id).execute()
                st.success("Deleted!")
                st.rerun()
    else:
        st.info("No manual expenses recorded yet.")

# --- TAB 3: BALANCE SHEET ---
with tab_bs:
    st.markdown("### ⚖️ Balance Sheet (Snapshot)")
    st.info("Current liabilities represent money collected from viewers but not yet disbursed to creators.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📉 Current Liabilities")
        st.metric("Accounts Payable (Pending Payouts)", format_inr(accounts_payable), help="Money owed to creators for generated but unpaid payouts.")
        
    with col2:
        st.markdown("#### 💸 Cash Flow (Outflows)")
        st.metric("Cash Disbursed (Paid Payouts)", format_inr(cash_disbursed))
        st.metric("Gateway Fees Paid to Razorpay", format_inr(total_gateway_fees))
        st.metric("Manual Expenses Paid", format_inr(total_expenses))

# --- TAB 4: CA EXPORT ---
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
            "Operating Profit (EBITDA)",
            "Total Manual Business Expenses",
            "Final Net Profit (Bottom Line)",
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
            operating_profit / 100,
            total_expenses / 100,
            final_net_profit / 100,
            accounts_payable / 100,
            cash_disbursed / 100
        ]
    }
    
    df_export = pd.DataFrame(export_data)
    st.dataframe(df_export, width="stretch", hide_index=True)
    
    csv = df_export.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Financial Summary (CSV)",
        data=csv,
        file_name=f"streamheart_financials_{datetime.date.today().isoformat()}.csv",
        mime="text/csv",
        width="stretch"
    )
