import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
from zoneinfo import ZoneInfo
from utils.supabase_client import supabase, fetch_all
from utils.auth import require_auth
from utils.helpers import format_inr

require_auth()

st.set_page_config(page_title="Platform Financials", page_icon="📊", layout="wide")
st.title("📊 StreamHeart Financials & Balance Sheet")
st.caption("Comprehensive P&L, Balance Sheet, and Expense tracking for StreamHeart Private Limited.")

# ==============================================================================
# 1. DATE RANGE & PRESETS
# ==============================================================================
IST = ZoneInfo("Asia/Kolkata")
today_ist = datetime.datetime.now(IST).date()

# Default to Current Financial Year (India: April 1 to March 31)
fy_start_year = today_ist.year if today_ist.month >= 4 else today_ist.year - 1
default_start = datetime.date(fy_start_year, 4, 1)
default_end = today_ist

# Use session state to allow preset buttons to update date inputs
if 'fin_start_date' not in st.session_state:
    st.session_state.fin_start_date = default_start
if 'fin_end_date' not in st.session_state:
    st.session_state.fin_end_date = default_end

st.markdown("### 📅 Select Financial Period")
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start Date", value=st.session_state.fin_start_date, key="start_widget")
with col2:
    end_date = st.date_input("End Date", value=st.session_state.fin_end_date, key="end_widget")

# Update session state if user manually changes dates
st.session_state.fin_start_date = start_date
st.session_state.fin_end_date = end_date

preset_col1, preset_col2, preset_col3, preset_col4 = st.columns(4)
with preset_col1:
    if st.button("Current Month", width="stretch"):
        st.session_state.fin_start_date = today_ist.replace(day=1)
        st.session_state.fin_end_date = today_ist
        st.rerun()
with preset_col2:
    if st.button("Last Month", width="stretch"):
        last_month_end = today_ist.replace(day=1) - datetime.timedelta(days=1)
        st.session_state.fin_start_date = last_month_end.replace(day=1)
        st.session_state.fin_end_date = last_month_end
        st.rerun()
with preset_col3:
    if st.button("Current FY (Apr-Mar)", width="stretch"):
        st.session_state.fin_start_date = default_start
        st.session_state.fin_end_date = today_ist
        st.rerun()
with preset_col4:
    if st.button("All Time (Lifetime)", width="stretch"):
        st.session_state.fin_start_date = datetime.date(2020, 1, 1)
        st.session_state.fin_end_date = today_ist
        st.rerun()

start_dt_ist = datetime.datetime.combine(start_date, datetime.time.min, tzinfo=IST)
end_dt_ist = datetime.datetime.combine(end_date, datetime.time.max, tzinfo=IST)
start_iso = start_dt_ist.astimezone(datetime.timezone.utc).isoformat()
end_iso = end_dt_ist.astimezone(datetime.timezone.utc).isoformat()

st.caption(f"🕒 Analyzing period: **{start_date.strftime('%d %b %Y')}** to **{end_date.strftime('%d %b %Y')}** (IST)")

# ==============================================================================
# 2. DATA FETCHING & CALCULATIONS
# ==============================================================================
with st.spinner("Aggregating financial data..."):
    # ✅ FIX: Using fetch_all to bypass 1000 row limit
    payments = fetch_all(lambda: supabase.table('payments').select(
        'amount_inr, fee_inr, tax_inr, creators:creator_id(payout_rate)'
    ).gte('created_at', start_iso).lte('created_at', end_iso))
        
    refunds_data = fetch_all(lambda: supabase.table('refunds').select('amount_inr')
        .gte('created_at', start_iso).lte('created_at', end_iso))
        
    payouts = fetch_all(lambda: supabase.table('payouts').select('creator_share_inr, status, created_at')
        .gte('created_at', start_iso).lte('created_at', end_iso))
        
    expenses = fetch_all(lambda: supabase.table('expenses').select('*')
        .gte('expense_date', start_date.isoformat()).lte('expense_date', end_date.isoformat()))

total_gmv = 0
total_expected_creator_share = 0
total_gateway_fees = 0

for p in payments:
    gross = p.get('amount_inr', 0) or 0
    total_gmv += gross
    
    creator_data = p.get('creators')
    if isinstance(creator_data, list) and len(creator_data) > 0: 
        rate = float(creator_data[0].get('payout_rate', 89))
    elif isinstance(creator_data, dict): 
        rate = float(creator_data.get('payout_rate', 89))
    else: 
        rate = 89.0
        
    total_expected_creator_share += gross * (rate / 100)
    total_gateway_fees += (p.get('fee_inr', 0) or 0) + (p.get('tax_inr', 0) or 0)

total_technical_refunds = sum(r.get('amount_inr', 0) or 0 for r in refunds_data)

# Net Revenue is the actual GMV (since refunds are already excluded from 'captured' payments in our clean ledger)
net_revenue = total_gmv 
gross_margin = net_revenue - total_expected_creator_share
operating_profit = gross_margin - total_gateway_fees

total_expenses = sum(e.get('amount_inr', 0) or 0 for e in expenses)
final_net_profit = operating_profit - total_expenses

# Accounts Payable (Unsettled Payouts)
accounts_payable = sum(p.get('creator_share_inr', 0) or 0 for p in payouts if p.get('status') == 'PENDING')

def acc_format(val):
    if val == "" or val is None: return ""
    val = float(val) / 100
    return f"₹ {val:,.2f}" if val >= 0 else f"(₹ {abs(val):,.2f})"

# ==============================================================================
# 3. UI TABS
# ==============================================================================
tab_simple, tab_dash, tab_stmts, tab_exp, tab_export = st.tabs([
    "💰 Simple Breakdown", "📊 Dashboard", "📑 Formal Statements", "💸 Expenses", "⬇️ CA Export"
])

with tab_simple:
    st.markdown("### 💰 StreamHeart's Take-Home Profit Calculator")
    breakdown_data = {
        "Step": [
            "1️⃣ Total Money Collected (Successful Donations)", 
            "2️⃣ Less: Paid to Creators (Their 89%/90% Share)", 
            "3️⃣ Less: Paid to Razorpay (Gateway Fees + GST)", 
            "4️⃣ Less: Company Bills (Logged Expenses)", 
            "🏆 StreamHeart's Final Take-Home Profit"
        ],
        "Amount (₹)": [
            net_revenue / 100, 
            - (total_expected_creator_share / 100), 
            - (total_gateway_fees / 100), 
            - (total_expenses / 100), 
            final_net_profit / 100
        ]
    }
    df_breakdown = pd.DataFrame(breakdown_data)
    
    def simple_format(val):
        return f"₹ {val:,.2f}" if val >= 0 else f"- ₹ {abs(val):,.2f}"
        
    df_breakdown['Amount (₹)'] = df_breakdown['Amount (₹)'].apply(simple_format)
    st.dataframe(df_breakdown, hide_index=True, width="stretch", column_config={
        "Step": st.column_config.TextColumn(width="large"),
        "Amount (₹)": st.column_config.TextColumn(width="medium")
    })
    
    st.info(f"💡 **How to read this:** Out of the **{format_inr(net_revenue)}** that successfully hit your bank account from viewers, you paid your creators and Razorpay their dues. After subtracting your company's manual bills (**{format_inr(total_expenses)}**), StreamHeart Private Limited is left with exactly **{format_inr(final_net_profit)}** in pure profit.")

with tab_dash:
    st.markdown("### 📈 Executive Summary")
    col1, col2, col3 = st.columns(3)
    col1.metric("Successful Revenue (GMV)", format_inr(net_revenue))
    col2.metric("Operating Profit (EBITDA)", format_inr(operating_profit))
    col3.metric("🔥 Final Net Profit", format_inr(final_net_profit), delta_color="normal" if final_net_profit >= 0 else "inverse")
    
    if total_expected_creator_share > 0 or total_gateway_fees > 0 or total_expenses > 0:
        fig = px.pie(
            names=["Creator Payouts (COGS)", "Gateway Fees", "Business Expenses", "Net Profit"], 
            values=[total_expected_creator_share, total_gateway_fees, total_expenses, max(0, final_net_profit)], 
            title=f"Cash Outflow & Revenue Distribution", 
            hole=0.4, 
            color_discrete_sequence=px.colors.sequential.Blues_r
        )
        st.plotly_chart(fig, width="stretch")

with tab_stmts:
    st.markdown("### 📑 Formal Financial Statements")
    
    st.markdown("#### 📊 Statement of Profit & Loss")
    is_data = {
        "Particulars": [
            "Gross Transaction Value (Successful GMV)", 
            "Net Revenue from Operations", 
            "Less: Creator Payouts (Cost of Services)", 
            "Gross Margin", 
            "Less: Payment Gateway Charges (Razorpay + GST)", 
            "Less: Operating & Administrative Expenses", 
            "NET PROFIT BEFORE TAX (NPBT)"
        ], 
        "Amount (₹)": [
            total_gmv, 
            net_revenue, 
            -total_expected_creator_share, 
            gross_margin, 
            -total_gateway_fees, 
            -total_expenses, 
            final_net_profit
        ]
    }
    df_is = pd.DataFrame(is_data)
    df_is['Amount (₹)'] = df_is['Amount (₹)'].apply(acc_format)
    st.dataframe(df_is, hide_index=True, width="stretch", column_config={
        "Particulars": st.column_config.TextColumn(width="large"),
        "Amount (₹)": st.column_config.TextColumn(width="medium")
    })
    
    st.divider()
    
    st.markdown("#### ⚖️ Balance Sheet")
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
    st.dataframe(df_bs, hide_index=True, width="stretch", column_config={
        "Particulars": st.column_config.TextColumn(width="large"),
        "Amount (₹)": st.column_config.TextColumn(width="medium")
    })

with tab_exp:
    st.markdown("### 💸 Manage Business Expenses")
    with st.form("add_expense_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            category = st.selectbox("Category", [
                "Server/Hosting", "Software/SaaS", "Marketing", 
                "Legal/Compliance", "Office/Admin", "Contractor/Freelancer", "Other"
            ])
        with c2:
            amount_rupees = st.number_input("Amount (INR ₹)", min_value=0.0, step=100.0, format="%.2f")
        with c3:
            expense_date = st.date_input("Date", value=datetime.date.today())
            
        description = st.text_input("Description / Notes", placeholder="e.g., AWS Monthly Bill")
        submitted = st.form_submit_button("➕ Add Expense", type="primary", width="stretch")
        
        if submitted:
            if amount_rupees <= 0:
                st.error("Amount must be greater than 0.")
            else:
                try:
                    supabase.table('expenses').insert({
                        "category": category, 
                        "description": description, 
                        "amount_inr": int(amount_rupees * 100), 
                        "expense_date": expense_date.isoformat()
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
        display_exp = df_exp[['id', 'Date', 'category', 'description', 'Amount (₹)']].rename(columns={
            'category': 'Category', 
            'description': 'Description'
        })
        st.dataframe(display_exp.drop(columns=['id']), width="stretch", hide_index=True)
    else:
        st.info("No expenses logged for this period.")

with tab_export:
    st.markdown("### ⬇️ Export for Chartered Accountant (CA)")
    st.caption("Download a clean CSV summary of your financials for tax filing and compliance.")
    
    export_data = {
        "Financial Metric": [
            "Successful GMV (Net Revenue)", 
            "Expected Creator Payouts (COGS)", 
            "Gross Margin", 
            "Gateway Fees", 
            "Operating Expenses", 
            "Net Profit (NPBT)", 
            "Accounts Payable", 
            "Technical Bank Failures (Off-Book)"
        ], 
        "Amount (INR)": [
            net_revenue/100, 
            total_expected_creator_share/100, 
            gross_margin/100, 
            total_gateway_fees/100, 
            total_expenses/100, 
            final_net_profit/100, 
            accounts_payable/100, 
            total_technical_refunds/100
        ]
    }
    df_export = pd.DataFrame(export_data)
    st.dataframe(df_export, width="stretch", hide_index=True)
    
    csv = df_export.to_csv(index=False).encode('utf-8')
    st.download_button(
        "📥 Download Financial Summary (CSV)", 
        data=csv, 
        file_name=f"streamheart_financials_{start_date}_to_{end_date}.csv", 
        mime="text/csv", 
        width="stretch"
    )
