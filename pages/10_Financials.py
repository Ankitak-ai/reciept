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

total_expenses = sum(e.get('amount_inr', 0) or 0 for e in expenses)
final_net_profit = operating_profit - total_expenses

accounts_payable = sum(p.get('creator_share_inr', 0) or 0 for p in payouts if p.get('status') == 'PENDING')
cash_disbursed = sum(p.get('creator_share_inr', 0) or 0 for p in payouts if p.get('status') == 'PAID')

# Helper for tabular accounting format (parentheses for negative numbers)
def acc_format(val):
    if val == "" or val is None: return ""
    val = float(val) / 100
    return f"₹ {val:,.2f}" if val >= 0 else f"(₹ {abs(val):,.2f})"

# ==============================================================================
# TABS
# ==============================================================================
tab_dash, tab_stmts, tab_exp, tab_export = st.tabs([
    "📊 Dashboard", "📑 Formal Statements", "💸 Expenses", "⬇️ CA Export"
])

# --- TAB 1: DASHBOARD ---
with tab_dash:
    st.markdown("### 📈 Executive Summary")
    col1, col2, col3 = st.columns(3)
    col1.metric("Net Revenue", format_inr(net_revenue))
    col2.metric("Operating Profit (EBITDA)", format_inr(operating_profit))
    col3.metric("🔥 Final Net Profit", format_inr(final_net_profit), delta_color="normal" if final_net_profit >= 0 else "inverse")
    
    if total_creator_payouts_generated > 0 or total_platform_commission > 0:
        fig = px.pie(
            names=["Creator Payouts", "Platform Commission", "Gateway Fees", "Business Expenses"],
            values=[total_creator_payouts_generated, total_platform_commission, total_gateway_fees, total_expenses],
            title="Cash Outflow & Revenue Distribution",
            hole=0.4,
            color_discrete_sequence=px.colors.sequential.Blues_r
        )
        st.plotly_chart(fig, width="stretch")

# --- TAB 2: FORMAL STATEMENTS (TABULAR DATA) ---
with tab_stmts:
    st.markdown("### 📑 Formal Financial Statements")
    st.caption("Standard accounting format for StreamHeart Private Limited (All figures in INR).")
    
    # 1. Statement of Profit & Loss
    st.markdown("#### 📊 Statement of Profit & Loss")
    is_data = {
        "Particulars": [
            "Gross Transaction Value (GMV)",
            "Less: Refunds & Chargebacks",
            "Net Revenue from Operations",
            "Less: Creator Payouts (Cost of Services)",
            "Gross Margin",
            "Less: Payment Gateway Charges (Razorpay + GST)",
            "Less: Operating & Administrative Expenses",
            "NET PROFIT BEFORE TAX (NPBT)"
        ],
        "Amount (₹)": [
            total_gmv,
            -total_refunds,
            net_revenue,
            -total_creator_payouts_generated,
            (net_revenue - total_creator_payouts_generated),
            -total_gateway_fees,
            -total_expenses,
            final_net_profit
        ]
    }
    df_is = pd.DataFrame(is_data)
    df_is['Amount (₹)'] = df_is['Amount (₹)'].apply(acc_format)
    
    # Highlight the final profit row
    st.dataframe(
        df_is, 
        hide_index=True, 
        width="stretch",
        column_config={
            "Particulars": st.column_config.TextColumn(width="large"),
            "Amount (₹)": st.column_config.TextColumn(width="medium", alignment="right")
        }
    )
    
    st.divider()
    
    # 2. Balance Sheet
    st.markdown("#### ⚖️ Balance Sheet (Statement of Financial Position)")
    bs_data = {
        "Particulars": [
            "CURRENT LIABILITIES",
            "Accounts Payable (Unsettled Creator Payouts)",
            "Total Current Liabilities",
            "",
            "EQUITY & RETAINED EARNINGS",
            "Retained Earnings (Cumulative Net Profit)",
            "Total Equity",
            "",
            "TOTAL LIABILITIES & EQUITY"
        ],
        "Amount (₹)": [
            "",
            accounts_payable,
            accounts_payable,
            "",
            "",
            final_net_profit,
            final_net_profit,
            "",
            (accounts_payable + final_net_profit)
        ]
    }
    df_bs = pd.DataFrame(bs_data)
    df_bs['Amount (₹)'] = df_bs['Amount (₹)'].apply(lambda x: acc_format(x) if x != "" else "")
    
    st.dataframe(
        df_bs, 
        hide_index=True, 
        width="stretch",
        column_config={
            "Particulars": st.column_config.TextColumn(width="large"),
            "Amount (₹)": st.column_config.TextColumn(width="medium", alignment="right")
        }
    )

# --- TAB 3: EXPENSES ---
with tab_exp:
    st.markdown("### 💸 Manage Business Expenses")
    
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
                try:
                    supabase.table('expenses').insert({
                        "category": category, "description": description,
                        "amount_inr": int(amount_rupees * 100), "expense_date": expense_date.isoformat()
                    }).execute()
                    st.success("✅ Expense added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to add expense: {e}")
                    
    st.divider()
    
    if expenses:
        df_exp = pd.DataFrame(expenses)
        df_exp['Amount (₹)'] = df_exp['amount_inr'].apply(lambda x: f"₹{x/100:,.2f}")
        df_exp['Date'] = pd.to_datetime(df_exp['expense_date']).dt.strftime('%d %b %Y')
        display_exp = df_exp[['id', 'Date', 'category', 'description', 'Amount (₹)']].rename(columns={'category': 'Category', 'description': 'Description'})
        st.dataframe(display_exp.drop(columns=['id']), width="stretch", hide_index=True)
        
        st.markdown("##### 🗑️ Remove Incorrect Expense")
        exp_options = {f"{row['Date']} | {row['Category']} | {row['Amount (₹)']} | {row['Description']}": row['id'] for _, row in display_exp.iterrows()}
        col_del1, col_del2 = st.columns([3, 1])
        with col_del1: selected_exp = st.selectbox("Select expense to delete", options=list(exp_options.keys()))
        with col_del2:
            st.write(""); st.write("")
            if st.button("Delete", type="secondary", width="stretch"):
                supabase.table('expenses').delete().eq('id', exp_options[selected_exp]).execute()
                st.rerun()
    else:
        st.info("No manual expenses recorded yet.")

# --- TAB 4: CA EXPORT ---
with tab_export:
    st.markdown("### ⬇️ Export for Chartered Accountant (CA)")
    export_data = {
        "Financial Metric": ["GMV", "Refunds", "Net Revenue", "Creator Payouts", "Platform Commission", "Gateway Fees", "Operating Expenses", "Net Profit", "Accounts Payable"],
        "Amount (INR)": [total_gmv/100, total_refunds/100, net_revenue/100, total_creator_payouts_generated/100, total_platform_commission/100, total_gateway_fees/100, total_expenses/100, final_net_profit/100, accounts_payable/100]
    }
    df_export = pd.DataFrame(export_data)
    st.dataframe(df_export, width="stretch", hide_index=True)
    
    csv = df_export.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Financial Summary (CSV)", data=csv, file_name=f"streamheart_financials_{datetime.date.today().isoformat()}.csv", mime="text/csv", width="stretch")
