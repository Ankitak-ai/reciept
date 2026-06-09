import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
from zoneinfo import ZoneInfo
from utils.supabase_client import supabase
from utils.auth import require_auth
from utils.helpers import format_inr

require_auth()

st.set_page_config(page_title="Investor Cockpit", page_icon="🦄", layout="wide")
st.title("🦄 Founder & Investor Cockpit")
st.caption("High-density SaaS & Creator Economy metrics for board updates, fundraising, and strategic planning.")

# ==============================================================================
# 1. DATE RANGE & PERIOD COMPARISON LOGIC
# ==============================================================================
IST = ZoneInfo("Asia/Kolkata")
today_ist = datetime.datetime.now(IST).date()

# Default to Current Month
default_start = today_ist.replace(day=1)
default_end = today_ist

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Current Period Start", value=default_start)
with col2:
    end_date = st.date_input("Current Period End", value=default_end)

# Automatically calculate the EXACT previous period for MoM comparison
delta_days = (end_date - start_date).days + 1
prev_end_date = start_date - datetime.timedelta(days=1)
prev_start_date = prev_end_date - datetime.timedelta(days=delta_days - 1)

st.caption(f"⚖️ **Comparing:** {start_date.strftime('%d %b')} to {end_date.strftime('%d %b')} **vs** {prev_start_date.strftime('%d %b')} to {prev_end_date.strftime('%d %b')}")

# Convert to UTC for Supabase
def to_utc_iso(d, is_end=False):
    dt = datetime.datetime.combine(d, datetime.time.max if is_end else datetime.time.min, tzinfo=IST)
    return dt.astimezone(datetime.timezone.utc).isoformat()

curr_start_iso = to_utc_iso(start_date)
curr_end_iso = to_utc_iso(end_date, True)
prev_start_iso = to_utc_iso(prev_start_date)
prev_end_iso = to_utc_iso(prev_end_date, True)

# ==============================================================================
# 2. DATA FETCHING
# ==============================================================================
with st.spinner("Crunching platform economics..."):
    # Fetch Current Period
    curr_pay_res = supabase.table('payments').select(
        'amount_inr, fee_inr, tax_inr, created_at, creator_id, creators:creator_id(creator_handle, payout_rate)'
    ).gte('created_at', curr_start_iso).lte('created_at', curr_end_iso).execute()
    curr_payments = curr_pay_res.data or []
    
    curr_ref_res = supabase.table('refunds').select('amount_inr').gte('created_at', curr_start_iso).lte('created_at', curr_end_iso).execute()
    curr_refunds = sum(r.get('amount_inr', 0) or 0 for r in (curr_ref_res.data or []))

    # Fetch Previous Period
    prev_pay_res = supabase.table('payments').select(
        'amount_inr, creator_id, creators:creator_id(payout_rate)'
    ).gte('created_at', prev_start_iso).lte('created_at', prev_end_iso).execute()
    prev_payments = prev_pay_res.data or []

# ==============================================================================
# 3. CORE METRIC CALCULATIONS (The VC Framework)
# ==============================================================================
def calc_metrics(payments_list):
    gmv = 0
    creator_payouts = 0
    gateway_fees = 0
    active_creators = set()
    creator_gmv_map = {}
    
    for p in payments_list:
        gross = p.get('amount_inr', 0) or 0
        gmv += gross
        gateway_fees += (p.get('fee_inr', 0) or 0) + (p.get('tax_inr', 0) or 0)
        
        cid = p.get('creator_id')
        if cid:
            active_creators.add(cid)
            creator_gmv_map[cid] = creator_gmv_map.get(cid, 0) + gross
            
            c_data = p.get('creators')
            rate = 89.0
            if isinstance(c_data, list) and len(c_data) > 0: rate = float(c_data[0].get('payout_rate', 89))
            elif isinstance(c_data, dict): rate = float(c_data.get('payout_rate', 89))
            
            creator_payouts += gross * (rate / 100)
            
    net_revenue = gmv - creator_payouts
    gross_profit = net_revenue - gateway_fees
    
    take_rate = (net_revenue / gmv * 100) if gmv > 0 else 0
    gross_margin = (gross_profit / net_revenue * 100) if net_revenue > 0 else 0
    
    # Top 5 Concentration
    sorted_creators = sorted(creator_gmv_map.values(), reverse=True)
    top_5_gmv = sum(sorted_creators[:5])
    top_5_concentration = (top_5_gmv / gmv * 100) if gmv > 0 else 0
    
    return {
        "gmv": gmv,
        "net_revenue": net_revenue,
        "gross_profit": gross_profit,
        "gateway_fees": gateway_fees,
        "take_rate": take_rate,
        "gross_margin": gross_margin,
        "active_creators": len(active_creators),
        "active_creator_ids": active_creators,
        "top_5_concentration": top_5_concentration,
        "txns": len(payments_list),
        "avg_donation": (gmv / len(payments_list)) if len(payments_list) > 0 else 0
    }

curr = calc_metrics(curr_payments)
prev = calc_metrics(prev_payments)

# MoM Deltas
def delta_pct(c, p):
    if p == 0: return "N/A" if c == 0 else "+∞"
    return f"{((c - p) / p) * 100:+.1f}%"

# Creator Retention (Intersection of current and previous active creators)
retained_creators = curr["active_creator_ids"].intersection(prev["active_creator_ids"])
creator_retention = (len(retained_creators) / prev["active_creators"] * 100) if prev["active_creators"] > 0 else 0

# Refund Rate
total_attempted_gmv = curr["gmv"] + curr_refunds
refund_rate = (curr_refunds / total_attempted_gmv * 100) if total_attempted_gmv > 0 else 0

# ==============================================================================
# 4. UI LAYOUT
# ==============================================================================
st.markdown("### 📊 Core Financials & Unit Economics")
c1, c2, c3, c4 = st.columns(4)
c1.metric("GMV (Gross Transaction Value)", format_inr(curr["gmv"]), delta=delta_pct(curr["gmv"], prev["gmv"]))
c2.metric("Net Revenue (Platform Take)", format_inr(curr["net_revenue"]), delta=delta_pct(curr["net_revenue"], prev["net_revenue"]))
c3.metric("Take Rate", f"{curr['take_rate']:.1f}%", help="Platform Revenue / GMV")
c4.metric("Gross Margin", f"{curr['gross_margin']:.1f}%", help="(Revenue - Gateway Fees) / Revenue", delta_color="normal" if curr['gross_margin'] > 70 else "inverse")

st.markdown("### 👥 Creator Economy Health")
c5, c6, c7, c8 = st.columns(4)
c5.metric("Active Creators", curr["active_creators"], delta=delta_pct(curr["active_creators"], prev["active_creators"]))
c6.metric("Creator Retention", f"{creator_retention:.0f}%", help="% of last period's creators who earned again this period")
c7.metric("Avg Donation Size", format_inr(curr["avg_donation"]))
c8.metric("Refund / Failure Rate", f"{refund_rate:.2f}%", delta_color="inverse" if refund_rate > 2 else "off")

# Top 5 Concentration Risk
st.markdown("### ⚠️ Revenue Concentration Risk")
if curr["top_5_concentration"] > 50:
    st.error(f"🚨 **High Dependency Risk:** Your Top 5 creators generate **{curr['top_5_concentration']:.1f}%** of total GMV. If one leaves, revenue drops significantly.")
elif curr["top_5_concentration"] > 30:
    st.warning(f"⚠️ **Moderate Concentration:** Top 5 creators generate **{curr['top_5_concentration']:.1f}%** of GMV. Aim to diversify.")
else:
    st.success(f"✅ **Healthy Diversification:** Top 5 creators generate only **{curr['top_5_concentration']:.1f}%** of GMV. Platform is well-balanced.")

# Charts
col_chart1, col_chart2 = st.columns(2)
with col_chart1:
    st.markdown("#### 📈 Daily GMV Trend (Current Period)")
    df_daily = pd.DataFrame(curr_payments)
    if not df_daily.empty:
        df_daily['ist_date'] = pd.to_datetime(df_daily['created_at']).dt.tz_convert(IST).dt.date
        daily_gmv = df_daily.groupby('ist_date')['amount_inr'].sum().reset_index()
        fig_line = px.line(daily_gmv, x='ist_date', y='amount_inr', labels={'amount_inr': 'GMV (₹)', 'ist_date': 'Date'})
        fig_line.update_layout(template="plotly_white", height=350)
        st.plotly_chart(fig_line, width="stretch")
    else:
        st.info("No daily data for chart.")

with col_chart2:
    st.markdown("#### 🍩 Creator Concentration Breakdown")
    if curr["gmv"] > 0:
        top_5_val = curr["gmv"] * (curr["top_5_concentration"] / 100)
        rest_val = curr["gmv"] - top_5_val
        fig_pie = px.pie(names=["Top 5 Creators", "All Other Creators"], values=[top_5_val, rest_val], hole=0.5)
        fig_pie.update_layout(template="plotly_white", height=350, showlegend=True)
        st.plotly_chart(fig_pie, width="stretch")
    else:
        st.info("No data for pie chart.")

st.divider()

# ==============================================================================
# 5. AUTOMATED INVESTOR EMAIL GENERATOR
# ==============================================================================
st.markdown("### ✉️ Auto-Generated Investor Update")
st.caption("Copy and paste this directly into your monthly email to stakeholders, board members, or VCs.")

period_str = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
gmv_delta = delta_pct(curr["gmv"], prev["gmv"])

email_text = f"""
Subject: StreamHeart Platform Metrics Update ({period_str})

Hi Team,

Here is the high-level performance overview for StreamHeart Private Limited for the period {period_str}.

📊 FINANCIALS & UNIT ECONOMICS
• GMV: {format_inr(curr['gmv'])} ({gmv_delta} vs prev period)
• Net Revenue (Platform Take): {format_inr(curr['net_revenue'])}
• Take Rate: {curr['take_rate']:.1f}%
• Gross Margin: {curr['gross_margin']:.1f}% (after absorbing gateway fees)
• Refund/Failure Rate: {refund_rate:.2f}%

👥 CREATOR ECONOMY HEALTH
• Active Creators: {curr['active_creators']} ({delta_pct(curr['active_creators'], prev['active_creators'])} vs prev period)
• Creator Retention: {creator_retention:.0f}% (Creators who earned in both periods)
• Average Donation Size: {format_inr(curr['avg_donation'])}
• Top 5 Concentration: {curr['top_5_concentration']:.1f}% 

💡 STRATEGIC NOTES
• [Add 1-2 sentences here about a new feature launched, a major creator signed, or a marketing push.]

Best,
Founder, StreamHeart Private Limited
"""

st.text_area("Investor Email Draft", email_text, height=400)
