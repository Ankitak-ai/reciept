import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime
from zoneinfo import ZoneInfo
from utils.supabase_client import supabase
from utils.auth import require_auth
from utils.helpers import format_inr

require_auth()

st.set_page_config(page_title="Growth & Forecasting", page_icon="🔮", layout="wide")
st.title("🔮 Growth Forecasting & Predictive Analytics")
st.caption("Using 30-day rolling averages and daily run-rates to predict realistic future cash flow.")

# Fetch all historical payments
with st.spinner("Analyzing historical growth patterns..."):
    payments_res = supabase.table('payments').select('amount_inr, created_at, creators:creator_id(creator_handle, payout_rate)').execute()
    payments = payments_res.data or []

if not payments:
    st.warning("Not enough historical data to generate forecasts yet. Keep collecting payments!")
    st.stop()

# Process Data
df = pd.DataFrame(payments)
df['created_at'] = pd.to_datetime(df['created_at'])
IST = ZoneInfo("Asia/Kolkata")
df['ist_date'] = df['created_at'].dt.tz_convert(IST).dt.date
df['amount_inr'] = df['amount_inr'].fillna(0)

# Extract creator info safely
def get_creator_info(row):
    c = row['creators']
    if isinstance(c, list) and len(c) > 0:
        return c[0].get('creator_handle', 'Unknown'), c[0].get('payout_rate', 89)
    elif isinstance(c, dict):
        return c.get('creator_handle', 'Unknown'), c.get('payout_rate', 89)
    return 'Unknown', 89

df[['creator_handle', 'payout_rate']] = df.apply(lambda row: pd.Series(get_creator_info(row)), axis=1)

# ==============================================================================
# 1. REALISTIC RUN-RATE FORECASTING
# ==============================================================================
today_ist = datetime.datetime.now(IST).date()
thirty_days_ago = today_ist - datetime.timedelta(days=30)

# Calculate Last 30 Days Performance
last_30_days_df = df[df['ist_date'] >= thirty_days_ago]
last_30_days_gmv = last_30_days_df['amount_inr'].sum()
active_days_in_last_30 = last_30_days_df['ist_date'].nunique()

# The "Run Rate" (Average per active day)
if active_days_in_last_30 > 0:
    daily_run_rate = last_30_days_gmv / active_days_in_last_30
else:
    daily_run_rate = 0

# Realistic Projection for NEXT 30 Days
projected_next_30_gmv = daily_run_rate * 30
projected_payout_liability = projected_next_30_gmv * 0.89  # Assuming avg 89% payout
projected_platform_revenue = projected_next_30_gmv * 0.11

# Compare to the 30 days BEFORE that (to get a realistic trend)
sixty_days_ago = today_ist - datetime.timedelta(days=60)
prev_30_days_df = df[(df['ist_date'] >= sixty_days_ago) & (df['ist_date'] < thirty_days_ago)]
prev_30_days_gmv = prev_30_days_df['amount_inr'].sum()

if prev_30_days_gmv > 0:
    realistic_mom_growth = ((last_30_days_gmv - prev_30_days_gmv) / prev_30_days_gmv) * 100
else:
    realistic_mom_growth = 0.0

# UI for Macro Forecast
st.markdown("### 📈 30-Day Run-Rate Projection")
st.info("💡 **How this works:** Instead of volatile month-over-month percentages, this engine calculates your exact average daily revenue over the last 30 days, and projects that exact pace forward. This is the standard metric used by SaaS and Fintech companies.")

c1, c2, c3 = st.columns(3)
c1.metric(
    "Projected GMV (Next 30 Days)", 
    format_inr(projected_next_30_gmv), 
    delta=f"{realistic_mom_growth:.1f}% vs prev 30d"
)
c2.metric(
    "Required Cash Reserve (Payouts)", 
    format_inr(projected_payout_liability), 
    help="Based on current run-rate, keep this much liquidity available for the next 30 days."
)
c3.metric(
    "Projected Platform Revenue", 
    format_inr(projected_platform_revenue)
)

st.caption(f"📊 **Data Maturity:** Based on **{active_days_in_last_30} active transaction days** in the last month. Daily Run-Rate: **{format_inr(daily_run_rate)}/day**.")

# Chart: Daily Dots + 7-Day Rolling Average Trendline
st.markdown("#### 📊 Daily Volume vs. Smoothed Trendline")
daily_gmv = df.groupby('ist_date')['amount_inr'].sum().reset_index()
daily_gmv = daily_gmv.sort_values('ist_date')

# Calculate 7-day rolling average to smooth out the "lumpiness" of daily donations
daily_gmv['7_Day_Avg'] = daily_gmv['amount_inr'].rolling(window=7, min_periods=1).mean()

fig = go.Figure()

# Raw Daily Dots (The Reality)
fig.add_trace(go.Scatter(
    x=daily_gmv['ist_date'], 
    y=daily_gmv['amount_inr']/100, 
    mode='markers',
    name='Daily Raw GMV',
    marker=dict(color='rgba(59, 130, 246, 0.4)', size=6)
))

# Smoothed Trendline (The True Direction)
fig.add_trace(go.Scatter(
    x=daily_gmv['ist_date'], 
    y=daily_gmv['7_Day_Avg']/100, 
    mode='lines',
    name='7-Day Rolling Average (Trend)',
    line=dict(color='#10b981', width=4)
))

fig.update_layout(
    yaxis_title="GMV (₹)",
    xaxis_title="Date",
    hovermode="x unified",
    template="plotly_white",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig, width="stretch")

st.divider()

# ==============================================================================
# 2. CREATOR MOMENTUM (Micro Analytics)
# ==============================================================================
st.markdown("### 🚀 Creator Momentum (Last 30 Days vs Previous 30 Days)")
st.caption("Identifying who is consistently growing and who is dropping off, based on 30-day rolling windows.")

# Filter to last 60 days for comparison
recent_df = df[df['ist_date'] >= sixty_days_ago].copy()
recent_df['period'] = recent_df['ist_date'].apply(lambda x: 'Last 30 Days' if x >= thirty_days_ago else 'Prev 30 Days')

creator_pivot = recent_df.groupby(['creator_handle', 'period'])['amount_inr'].sum().unstack(fill_value=0)

if 'Last 30 Days' in creator_pivot.columns and 'Prev 30 Days' in creator_pivot.columns:
    creator_pivot['Absolute Change'] = creator_pivot['Last 30 Days'] - creator_pivot['Prev 30 Days']
    
    def calc_safe_growth(row):
        if row['Prev 30 Days'] == 0: return 1.0 if row['Last 30 Days'] > 0 else 0.0
        return (row['Last 30 Days'] - row['Prev 30 Days']) / row['Prev 30 Days']
        
    creator_pivot['Growth %'] = creator_pivot.apply(calc_safe_growth, axis=1)
    
    # Filter for creators with meaningful volume (e.g., at least ₹1000 in the last 30 days)
    active_creators = creator_pivot[creator_pivot['Last 30 Days'] >= 10000] 
    
    tab_stars, tab_risk = st.tabs(["🌟 Rising Stars (Top Growth)", "⚠️ Churn Risk (Declining)"])
    
    with tab_stars:
        stars = active_creators.sort_values('Growth %', ascending=False).head(10)
        stars = stars[stars['Growth %'] > 0]
        if not stars.empty:
            display_stars = stars[['Last 30 Days', 'Prev 30 Days', 'Growth %', 'Absolute Change']].reset_index()
            display_stars['Last 30 Days'] = display_stars['Last 30 Days'].apply(lambda x: format_inr(x))
            display_stars['Prev 30 Days'] = display_stars['Prev 30 Days'].apply(lambda x: format_inr(x))
            display_stars['Absolute Change'] = display_stars['Absolute Change'].apply(lambda x: format_inr(x))
            display_stars['Growth %'] = display_stars['Growth %'].apply(lambda x: f"+{x*100:.1f}%")
            display_stars = display_stars.rename(columns={'creator_handle': 'Creator'})
            st.dataframe(display_stars, hide_index=True, width="stretch")
        else:
            st.info("No rising stars with significant volume detected in the last 30 days.")
            
    with tab_risk:
        risk = active_creators.sort_values('Growth %', ascending=True).head(10)
        risk = risk[risk['Growth %'] < 0] 
        if not risk.empty:
            display_risk = risk[['Last 30 Days', 'Prev 30 Days', 'Growth %', 'Absolute Change']].reset_index()
            display_risk['Last 30 Days'] = display_risk['Last 30 Days'].apply(lambda x: format_inr(x))
            display_risk['Prev 30 Days'] = display_risk['Prev 30 Days'].apply(lambda x: format_inr(x))
            display_risk['Absolute Change'] = display_risk['Absolute Change'].apply(lambda x: format_inr(x))
            display_risk['Growth %'] = display_risk['Growth %'].apply(lambda x: f"{x*100:.1f}%")
            display_risk = display_risk.rename(columns={'creator_handle': 'Creator'})
            st.dataframe(display_risk, hide_index=True, width="stretch")
        else:
            st.success("No major churn risks detected. All active creators are stable or growing!")
else:
    st.info("Need at least 30 to 60 days of historical data to calculate accurate 30-day rolling momentum.")
