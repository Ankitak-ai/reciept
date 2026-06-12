import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime
from zoneinfo import ZoneInfo
from utils.supabase_client import supabase
from utils.auth import require_auth
from utils.helpers import format_inr

require_auth()

st.set_page_config(page_title="Daily Revenue Tracker", page_icon="📊", layout="wide")
st.title("📊 Daily Revenue Tracker")
st.caption("Track your day-by-day GMV, transaction volume, and platform momentum.")

# ==============================================================================
# 1. DATE RANGE SELECTION
# ==============================================================================
IST = ZoneInfo("Asia/Kolkata")
today_ist = datetime.datetime.now(IST).date()

# Default to last 30 days
default_start = today_ist - datetime.timedelta(days=30)
default_end = today_ist

st.markdown("### 📅 Select Tracking Period")
col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    start_date = st.date_input("Start Date", value=default_start)
with col2:
    end_date = st.date_input("End Date", value=default_end)
with col3:
    st.write("")
    st.write("")
    if st.button("Last 7 Days", use_container_width=True):
        start_date = today_ist - datetime.timedelta(days=7)
        end_date = today_ist
        st.rerun()

# Convert to UTC for Supabase
start_dt_ist = datetime.datetime.combine(start_date, datetime.time.min, tzinfo=IST)
end_dt_ist = datetime.datetime.combine(end_date, datetime.time.max, tzinfo=IST)
start_iso = start_dt_ist.astimezone(datetime.timezone.utc).isoformat()
end_iso = end_dt_ist.astimezone(datetime.timezone.utc).isoformat()

# ==============================================================================
# 2. DATA FETCHING & PROCESSING
# ==============================================================================
with st.spinner("Loading daily revenue data..."):
    payments_res = supabase.table('payments').select(
        'amount_inr, fee_inr, created_at'
    ).gte('created_at', start_iso).lte('created_at', end_iso).execute()
    
    payments = payments_res.data or []

if not payments:
    st.warning(f"No payments found between {start_date.strftime('%d %b')} and {end_date.strftime('%d %b')}.")
    st.stop()

# Process into DataFrame
df = pd.DataFrame(payments)
df['created_at'] = pd.to_datetime(df['created_at'])

# Convert UTC to IST date for grouping
df['ist_date'] = df['created_at'].dt.tz_convert(IST).dt.date
df['amount_inr'] = df['amount_inr'].fillna(0)
df['fee_inr'] = df['fee_inr'].fillna(0)

# Group by day
daily_stats = df.groupby('ist_date').agg(
    daily_gmv=('amount_inr', 'sum'),
    daily_txns=('amount_inr', 'count'),
    daily_fees=('fee_inr', 'sum'),
    avg_donation=('amount_inr', 'mean')
).reset_index()

daily_stats = daily_stats.sort_values('ist_date')

# Calculate period totals for metrics
total_gmv = daily_stats['daily_gmv'].sum()
total_txns = daily_stats['daily_txns'].sum()
total_fees = daily_stats['daily_fees'].sum()
avg_daily_gmv = daily_stats['daily_gmv'].mean()

# Find peak day
peak_day_idx = daily_stats['daily_gmv'].idxmax()
peak_day_date = daily_stats.loc[peak_day_idx, 'ist_date']
peak_day_gmv = daily_stats.loc[peak_day_idx, 'daily_gmv']

# ==============================================================================
# 3. EXECUTIVE METRICS
# ==============================================================================
st.markdown("### 📈 Period Overview")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total GMV", format_inr(total_gmv))
c2.metric("Total Transactions", f"{total_txns:,}")
c3.metric("Avg Daily GMV", format_inr(avg_daily_gmv))
c4.metric("Gateway Fees Paid", format_inr(total_fees))

st.divider()

# ==============================================================================
# 4. THE HERO CHART (Daily GMV + Transaction Count)
# ==============================================================================
st.markdown("### 💰 Daily GMV & Transaction Volume")

# Create figure with secondary y-axis for transactions
fig = go.Figure()

# Bar chart for GMV
fig.add_trace(go.Bar(
    x=daily_stats['ist_date'],
    y=daily_stats['daily_gmv']/100,
    name='Daily GMV (₹)',
    marker_color='#3b82f6',
    opacity=0.8,
    yaxis='y'
))

# Line chart for transaction count overlay
fig.add_trace(go.Scatter(
    x=daily_stats['ist_date'],
    y=daily_stats['daily_txns'],
    name='Transaction Count',
    marker_color='#f59e0b',
    line=dict(width=3),
    yaxis='y2'
))

fig.update_layout(
    title=f"Daily Revenue Pulse ({start_date.strftime('%d %b')} - {end_date.strftime('%d %b')})",
    xaxis_title="Date",
    yaxis=dict(
        title="GMV (₹)",
        titlefont=dict(color='#3b82f6'),
        tickfont=dict(color='#3b82f6'),
    ),
    yaxis2=dict(
        title="Transactions",
        titlefont=dict(color='#f59e0b'),
        tickfont=dict(color='#f59e0b'),
        overlaying="y",
        side="right"
    ),
    hovermode="x unified",
    template="plotly_white",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    height=500
)

st.plotly_chart(fig, width="stretch")

# ==============================================================================
# 5. DAILY BREAKDOWN TABLE
# ==============================================================================
st.markdown("### 📋 Daily Breakdown Ledger")

display_df = daily_stats.copy()
display_df['Date'] = pd.to_datetime(display_df['ist_date']).dt.strftime('%d %b %Y (%a)')
display_df['GMV (₹)'] = display_df['daily_gmv'].apply(lambda x: format_inr(x))
display_df['Avg Donation'] = display_df['avg_donation'].apply(lambda x: format_inr(x))
display_df['Fees'] = display_df['daily_fees'].apply(lambda x: format_inr(x))

display_cols = ['Date', 'daily_txns', 'GMV (₹)', 'Avg Donation', 'Fees']
display_df = display_df[display_cols].rename(columns={'daily_txns': 'Txns'})

# Reverse so newest day is at the top
display_df = display_df.sort_index(ascending=False)

st.dataframe(display_df, hide_index=True, width="stretch")

# ==============================================================================
# 6. INSIGHTS
# ==============================================================================
st.divider()
st.markdown("### 💡 Quick Insights")

col_i1, col_i2 = st.columns(2)
with col_i1:
    st.info(f"🏆 **Peak Revenue Day:** {peak_day_date.strftime('%d %b %Y')} with **{format_inr(peak_day_gmv)}** in GMV.")
with col_i2:
    active_days = len(daily_stats)
    zero_days = (end_date - start_date).days + 1 - active_days
    st.info(f"📊 **Active Trading Days:** {active_days} out of {(end_date - start_date).days + 1} days in this period.")
