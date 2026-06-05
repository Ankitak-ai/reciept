import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
from zoneinfo import ZoneInfo
from utils.supabase_client import supabase
from utils.auth import require_auth
from utils.helpers import format_inr

require_auth()

st.set_page_config(page_title="Daily Operations Report", page_icon="📈", layout="wide")
st.title("📈 Daily Operations & Comparison Report")

# ==============================================================================
# 1. DATE SELECTION & IST TIMEZONE MATH
# ==============================================================================
IST = ZoneInfo("Asia/Kolkata")
now_ist = datetime.datetime.now(IST)
today_ist_date = now_ist.date()
yesterday_ist_date = today_ist_date - datetime.timedelta(days=1)

st.markdown("### 📅 Select Dates to Analyze")
col_sel1, col_sel2 = st.columns(2)
with col_sel1:
    primary_date = st.date_input("Primary Date (Focus)", value=today_ist_date, help="The main day you want to analyze.")
with col_sel2:
    comparison_date = st.date_input("Comparison Date", value=yesterday_ist_date, help="The day to compare against (for Day-over-Day metrics).")

# Create exact IST boundaries for the selected dates
primary_start_ist = datetime.datetime.combine(primary_date, datetime.time.min, tzinfo=IST)
primary_end_ist = datetime.datetime.combine(primary_date, datetime.time.max, tzinfo=IST)

comparison_start_ist = datetime.datetime.combine(comparison_date, datetime.time.min, tzinfo=IST)
comparison_end_ist = datetime.datetime.combine(comparison_date, datetime.time.max, tzinfo=IST)

# Convert to UTC for Supabase Queries
primary_start_utc = primary_start_ist.astimezone(datetime.timezone.utc).isoformat()
primary_end_utc = primary_end_ist.astimezone(datetime.timezone.utc).isoformat()

comparison_start_utc = comparison_start_ist.astimezone(datetime.timezone.utc).isoformat()
comparison_end_utc = comparison_end_ist.astimezone(datetime.timezone.utc).isoformat()

st.caption(f"🕒 Analyzing: **{primary_date.strftime('%A, %d %B %Y')}** vs **{comparison_date.strftime('%A, %d %B %Y')}** (IST)")

# ==============================================================================
# 2. DATA FETCHING
# ==============================================================================
with st.spinner("Crunching the numbers..."):
    # Fetch Primary Date Payments
    pay_primary_res = supabase.table('payments').select('amount_inr, fee_inr, tax_inr, created_at')\
        .gte('created_at', primary_start_utc).lte('created_at', primary_end_utc).execute()
    pay_primary = pay_primary_res.data or []

    # Fetch Comparison Date Payments
    pay_comp_res = supabase.table('payments').select('amount_inr, fee_inr, tax_inr')\
        .gte('created_at', comparison_start_utc).lte('created_at', comparison_end_utc).execute()
    pay_comp = pay_comp_res.data or []

    # Fetch Primary Date Refunds
    ref_primary_res = supabase.table('refunds').select('amount_inr')\
        .gte('created_at', primary_start_utc).lte('created_at', primary_end_utc).execute()
    ref_primary = ref_primary_res.data or []

    # Fetch New Creators on Primary Date
    new_creators_res = supabase.table('creators').select('id')\
        .gte('created_at', primary_start_utc).lte('created_at', primary_end_utc).execute()
    new_creators_primary = len(new_creators_res.data or [])

# ==============================================================================
# 3. CALCULATIONS & COMPARISON METRICS
# ==============================================================================
primary_gmv = sum(p.get('amount_inr', 0) or 0 for p in pay_primary)
comp_gmv = sum(p.get('amount_inr', 0) or 0 for p in pay_comp)

primary_fees = sum((p.get('fee_inr', 0) or 0) + (p.get('tax_inr', 0) or 0) for p in pay_primary)
primary_refunds = sum(r.get('amount_inr', 0) or 0 for r in ref_primary)
primary_txn_count = len(pay_primary)
comp_txn_count = len(pay_comp)

# Helper for Delta %
def calc_delta(primary, comparison):
    if comparison == 0:
        return "N/A" if primary == 0 else "+∞"
    return f"{((primary - comparison) / comparison) * 100:.1f}%"

delta_gmv = calc_delta(primary_gmv, comp_gmv)
delta_txns = calc_delta(primary_txn_count, comp_txn_count)

# Safely initialize peak hour variables for the report
peak_hour_str = "No activity on this day"

# ==============================================================================
# 4. UI LAYOUT
# ==============================================================================
tab_metrics, tab_hourly, tab_export = st.tabs(["📊 Executive Summary", "⏰ Hourly Heatmap", "📋 Shareable Report"])

# --- TAB 1: METRICS ---
with tab_metrics:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Primary Date GMV", format_inr(primary_gmv), delta=delta_gmv, help=f"Compared to {comparison_date.strftime('%d %b')}")
    c2.metric("Total Transactions", primary_txn_count, delta=delta_txns)
    c3.metric("Gateway Fees Paid", format_inr(primary_fees))
    c4.metric("Refunds Processed", format_inr(primary_refunds), delta_color="inverse" if primary_refunds > 0 else "off")

    st.divider()
    c5, c6 = st.columns(2)
    c5.metric("Net Revenue (GMV - Refunds)", format_inr(primary_gmv - primary_refunds))
    c6.metric("New Creators Onboarded", new_creators_primary)

# --- TAB 2: HOURLY HEATMAP (Primary Date) ---
with tab_hourly:
    st.markdown(f"### ⏰ Transaction Volume by Hour ({primary_date.strftime('%d %b %Y')} IST)")
    st.caption("Identify peak streaming and donation hours for the primary date.")
    
    if pay_primary:
        df_hourly = pd.DataFrame(pay_primary)
        # Convert UTC created_at back to IST hour
        df_hourly['ist_hour'] = pd.to_datetime(df_hourly['created_at']).dt.tz_convert(IST).dt.hour
        
        hourly_counts = df_hourly.groupby('ist_hour').size().reset_index(name='count')
        
        # Ensure all 24 hours are represented for a clean chart
        all_hours = pd.DataFrame({'ist_hour': range(24)})
        hourly_counts = pd.merge(all_hours, hourly_counts, on='ist_hour', how='left').fillna(0)
        
        # Calculate peak hour safely
        if hourly_counts['count'].max() > 0:
            max_idx = hourly_counts['count'].idxmax()
            peak_hr = int(hourly_counts.loc[max_idx, 'ist_hour'])
            peak_txns = int(hourly_counts.loc[max_idx, 'count'])
            peak_hour_str = f"{peak_hr:02d}:00 IST ({peak_txns} txns)"
        
        fig = px.bar(
            hourly_counts, 
            x='ist_hour', 
            y='count',
            labels={'ist_hour': 'Hour of Day (IST)', 'count': 'Number of Donations'},
            color='count',
            color_continuous_scale='blues'
        )
        fig.update_layout(xaxis=dict(dtick=1))
        st.plotly_chart(fig, width="stretch")
    else:
        st.info(f"No transactions recorded on {primary_date}.")

# --- TAB 3: SHAREABLE REPORT ---
with tab_export:
    st.markdown("### 📋 Shareable Performance Report")
    st.caption("Copy this formatted text and paste it directly into your team's WhatsApp, Slack, or Email.")
    
    # Calculate Platform Net for the day (Rough est based on 11% avg platform cut)
    platform_comm_primary = (primary_gmv - primary_refunds) * 0.11 
    
    eod_text = f"""
📊 *StreamHeart Performance Report*
🗓 *Focus Date:* {primary_date.strftime('%d %b %Y')} (IST)
⚖️ *Compared to:* {comparison_date.strftime('%d %b %Y')}

💰 *FINANCIALS*
• Gross Volume (GMV): {format_inr(primary_gmv)} ({delta_gmv} vs comp)
• Net Volume (After Refunds): {format_inr(primary_gmv - primary_refunds)}
• Gateway Fees Paid: {format_inr(primary_fees)}
• Refunds Issued: {format_inr(primary_refunds)}

🧾 *OPERATIONS*
• Total Transactions: {primary_txn_count} ({delta_txns} vs comp)
• New Creators Onboarded: {new_creators_primary}

⏰ *PEAK ACTIVITY*
• Highest Volume Hour: {peak_hour_str}

_Generated automatically by StreamHeart Finance Infrastructure._
    """
    
    st.text_area("Report Text (Click inside to copy)", eod_text, height=350)
    
    st.download_button(
        label="⬇️ Download as .txt",
        data=eod_text,
        file_name=f"StreamHeart_Report_{primary_date.strftime('%Y-%m-%d')}.txt",
        mime="text/plain",
        width="stretch"
    )
