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
st.title("📈 Daily Operations Report")

# ==============================================================================
# 1. IST TIMEZONE MATH (Crucial for accurate daily boundaries)
# ==============================================================================
IST = ZoneInfo("Asia/Kolkata")
now_ist = datetime.datetime.now(IST)

# Today's Boundaries (IST)
today_start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
today_end_ist = now_ist.replace(hour=23, minute=59, second=59, microsecond=999999)

# Yesterday's Boundaries (IST)
yesterday_start_ist = today_start_ist - datetime.timedelta(days=1)
yesterday_end_ist = today_start_ist - datetime.timedelta(microseconds=1)

# Convert to UTC for Supabase Queries
today_start_utc = today_start_ist.astimezone(datetime.timezone.utc).isoformat()
today_end_utc = today_end_ist.astimezone(datetime.timezone.utc).isoformat()
yesterday_start_utc = yesterday_start_ist.astimezone(datetime.timezone.utc).isoformat()
yesterday_end_utc = yesterday_end_ist.astimezone(datetime.timezone.utc).isoformat()

st.caption(f"🕒 Reporting for: **{now_ist.strftime('%A, %d %B %Y')}** (IST)")

# ==============================================================================
# 2. DATA FETCHING
# ==============================================================================
with st.spinner("Crunching today's numbers..."):
    # Fetch Today's Payments
    pay_today_res = supabase.table('payments').select('amount_inr, fee_inr, tax_inr, created_at')\
        .gte('created_at', today_start_utc).lte('created_at', today_end_utc).execute()
    pay_today = pay_today_res.data or []

    # Fetch Yesterday's Payments
    pay_yest_res = supabase.table('payments').select('amount_inr, fee_inr, tax_inr')\
        .gte('created_at', yesterday_start_utc).lte('created_at', yesterday_end_utc).execute()
    pay_yest = pay_yest_res.data or []

    # Fetch Today's Refunds
    ref_today_res = supabase.table('refunds').select('amount_inr')\
        .gte('created_at', today_start_utc).lte('created_at', today_end_utc).execute()
    ref_today = ref_today_res.data or []

    # Fetch New Creators Today
    new_creators_res = supabase.table('creators').select('id')\
        .gte('created_at', today_start_utc).lte('created_at', today_end_utc).execute()
    new_creators_today = len(new_creators_res.data or [])

# ==============================================================================
# 3. CALCULATIONS & DAY-OVER-DAY (DoD) METRICS
# ==============================================================================
today_gmv = sum(p.get('amount_inr', 0) or 0 for p in pay_today)
yest_gmv = sum(p.get('amount_inr', 0) or 0 for p in pay_yest)

today_fees = sum((p.get('fee_inr', 0) or 0) + (p.get('tax_inr', 0) or 0) for p in pay_today)
today_refunds = sum(r.get('amount_inr', 0) or 0 for r in ref_today)
today_txn_count = len(pay_today)
yest_txn_count = len(pay_yest)

# Helper for Delta %
def calc_delta(today, yesterday):
    if yesterday == 0:
        return "N/A" if today == 0 else "+∞"
    return f"{((today - yesterday) / yesterday) * 100:.1f}%"

delta_gmv = calc_delta(today_gmv, yest_gmv)
delta_txns = calc_delta(today_txn_count, yest_txn_count)

# ==============================================================================
# 4. UI LAYOUT
# ==============================================================================
tab_metrics, tab_hourly, tab_export = st.tabs(["📊 Executive Summary", "⏰ Hourly Heatmap", "📋 Shareable EOD Report"])

# --- TAB 1: METRICS ---
with tab_metrics:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Today's Gross Volume (GMV)", format_inr(today_gmv), delta=delta_gmv)
    c2.metric("Total Transactions", today_txn_count, delta=delta_txns)
    c3.metric("Gateway Fees Paid", format_inr(today_fees))
    c4.metric("Refunds Processed", format_inr(today_refunds), delta_color="inverse" if today_refunds > 0 else "off")

    st.divider()
    c5, c6 = st.columns(2)
    c5.metric("Net Revenue (GMV - Refunds)", format_inr(today_gmv - today_refunds))
    c6.metric("New Creators Onboarded", new_creators_today)

# --- TAB 2: HOURLY HEATMAP ---
with tab_hourly:
    st.markdown("### ⏰ Transaction Volume by Hour (IST)")
    st.caption("Identify peak streaming and donation hours.")
    
    if pay_today:
        df_hourly = pd.DataFrame(pay_today)
        # Convert UTC created_at back to IST hour
        df_hourly['ist_hour'] = pd.to_datetime(df_hourly['created_at']).dt.tz_convert(IST).dt.hour
        
        hourly_counts = df_hourly.groupby('ist_hour').size().reset_index(name='count')
        
        # Ensure all 24 hours are represented for a clean chart
        all_hours = pd.DataFrame({'ist_hour': range(24)})
        hourly_counts = pd.merge(all_hours, hourly_counts, on='ist_hour', how='left').fillna(0)
        
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
        st.info("No transactions recorded yet today.")

# --- TAB 3: SHAREABLE EOD REPORT ---
with tab_export:
    st.markdown("### 📋 Shareable End-of-Day (EOD) Summary")
    st.caption("Copy this formatted text and paste it directly into your team's WhatsApp, Slack, or Email.")
    
    # Calculate Platform Net for the day
    platform_comm_today = (today_gmv - today_refunds) * 0.11 # Rough est based on 89% avg payout
    
    eod_text = f"""
📊 *StreamHeart Daily Ops Report*
🗓 *Date:* {now_ist.strftime('%d %b %Y')} (IST)

💰 *FINANCIALS*
• Gross Volume (GMV): {format_inr(today_gmv)} ({delta_gmv} vs yesterday)
• Net Volume (After Refunds): {format_inr(today_gmv - today_refunds)}
• Gateway Fees Paid: {format_inr(today_fees)}
• Refunds Issued: {format_inr(today_refunds)}

🧾 *OPERATIONS*
• Total Transactions: {today_txn_count} ({delta_txns} vs yesterday)
• New Creators Onboarded: {new_creators_today}

⏰ *PEAK ACTIVITY*
• Highest Volume Hour: {hourly_counts.loc[hourly_counts['count'].idxmax()]['ist_hour']:02.0f}:00 IST ({int(hourly_counts['count'].max())} txns)

_Generated automatically by StreamHeart Finance Infrastructure._
    """
    
    st.text_area("Report Text (Click to copy)", eod_text, height=350)
    
    st.download_button(
        label="⬇️ Download as .txt",
        data=eod_text,
        file_name=f"StreamHeart_Daily_Report_{now_ist.strftime('%Y-%m-%d')}.txt",
        mime="text/plain",
        width="stretch"
    )
