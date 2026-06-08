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
st.caption("Using historical momentum to predict future cash flow and identify creator trends.")

# Fetch all historical payments
with st.spinner("Analyzing historical growth patterns..."):
    payments_res = supabase.table('payments').select('amount_inr, created_at, creators:creator_id(creator_handle, creator_code, payout_rate)').execute()
    payments = payments_res.data or []

if not payments:
    st.warning("Not enough historical data to generate forecasts yet. Keep collecting payments!")
    st.stop()

# Process Data
df = pd.DataFrame(payments)
df['created_at'] = pd.to_datetime(df['created_at'])
IST = ZoneInfo("Asia/Kolkata")
df['ist_date'] = df['created_at'].dt.tz_convert(IST).dt.date
df['month'] = df['ist_date'].apply(lambda x: x.replace(day=1)) # Group by 1st of the month
df['amount_inr'] = df['amount_inr'].fillna(0)

# Extract creator info and payout rate safely
def get_creator_info(row):
    c = row['creators']
    if isinstance(c, list) and len(c) > 0:
        return c[0].get('creator_handle', 'Unknown'), c[0].get('payout_rate', 89)
    elif isinstance(c, dict):
        return c.get('creator_handle', 'Unknown'), c.get('payout_rate', 89)
    return 'Unknown', 89

df[['creator_handle', 'payout_rate']] = df.apply(lambda row: pd.Series(get_creator_info(row)), axis=1)

# ==============================================================================
# 1. MACRO FORECAST (Next Month Prediction)
# ==============================================================================
monthly_gmv = df.groupby('month')['amount_inr'].sum().reset_index()
monthly_gmv = monthly_gmv.sort_values('month')

# Simple Moving Average / Linear Trend for next month prediction
if len(monthly_gmv) >= 2:
    monthly_gmv['growth'] = monthly_gmv['amount_inr'].pct_change()
    avg_growth = monthly_gmv['growth'].mean()
    
    # If negative or NaN, assume conservative 5% growth
    if pd.isna(avg_growth) or avg_growth < 0:
        forecast_growth = 0.05 
    else:
        forecast_growth = avg_growth
        
    last_month_gmv = monthly_gmv['amount_inr'].iloc[-1]
    next_month_predicted_gmv = last_month_gmv * (1 + forecast_growth)
else:
    next_month_predicted_gmv = monthly_gmv['amount_inr'].sum()
    forecast_growth = 0

# Calculate expected payout liability (assume avg 89% payout rate)
expected_payout_liability = next_month_predicted_gmv * 0.89
expected_platform_revenue = next_month_predicted_gmv * 0.11

# UI for Macro Forecast
st.markdown("### 📈 Next Month Cash Flow Projection")
c1, c2, c3 = st.columns(3)
c1.metric("Predicted GMV (Next 30 Days)", format_inr(next_month_predicted_gmv), delta=f"{forecast_growth*100:.1f}% MoM Momentum")
c2.metric("Required Cash Reserve (Payouts)", format_inr(expected_payout_liability), help="Ensure this much cash is available for next month's creator settlements.")
c3.metric("Projected Platform Revenue", format_inr(expected_platform_revenue))

# Chart: Historical + Forecast
st.markdown("#### 📊 GMV Trend & Forecast")
fig = go.Figure()

# Historical Line
fig.add_trace(go.Scatter(
    x=monthly_gmv['month'], 
    y=monthly_gmv['amount_inr']/100, 
    mode='lines+markers',
    name='Historical GMV',
    line=dict(color='#3b82f6', width=3)
))

# Forecast Dotted Line
if len(monthly_gmv) > 0:
    last_date = monthly_gmv['month'].iloc[-1]
    next_month_date = (last_date + datetime.timedelta(days=32)).replace(day=1)
    
    fig.add_trace(go.Scatter(
        x=[last_date, next_month_date],
        y=[monthly_gmv['amount_inr'].iloc[-1]/100, next_month_predicted_gmv/100],
        mode='lines+markers',
        name='Predicted (Momentum)',
        line=dict(color='#10b981', width=3, dash='dash')
    ))

fig.update_layout(
    yaxis_title="GMV (₹)",
    xaxis_title="Month",
    hovermode="x unified",
    template="plotly_white"
)
st.plotly_chart(fig, width="stretch")

st.divider()

# ==============================================================================
# 2. CREATOR MOMENTUM (Micro Analytics)
# ==============================================================================
st.markdown("### 🚀 Creator Momentum & Churn Risk")
st.caption("Identifying who is growing fastest (Stars) and who is dropping off (At-Risk).")

# Calculate MoM growth per creator
creator_monthly = df.groupby(['creator_handle', 'month'])['amount_inr'].sum().reset_index()
creator_pivot = creator_monthly.pivot(index='creator_handle', columns='month', values='amount_inr').fillna(0)

if creator_pivot.shape[1] >= 2:
    creator_pivot = creator_pivot.sort_index(axis=1)
    last_m = creator_pivot.columns[-1]
    prev_m = creator_pivot.columns[-2]
    
    creator_pivot['Last Month GMV'] = creator_pivot[last_m]
    creator_pivot['Prev Month GMV'] = creator_pivot[prev_m]
    
    def calc_growth(row):
        if row['Prev Month GMV'] == 0: return 1.0 if row['Last Month GMV'] > 0 else 0.0
        return (row['Last Month GMV'] - row['Prev Month GMV']) / row['Prev Month GMV']
        
    creator_pivot['MoM Growth %'] = creator_pivot.apply(calc_growth, axis=1)
    creator_pivot['Absolute Change'] = creator_pivot['Last Month GMV'] - creator_pivot['Prev Month GMV']
    
    # Filter out creators with negligible volume to avoid 1000% growth on ₹10
    active_creators = creator_pivot[creator_pivot['Last Month GMV'] > 5000] 
    
    tab_stars, tab_risk = st.tabs(["🌟 Rising Stars (Top Growth)", "⚠️ Churn Risk (Declining)"])
    
    with tab_stars:
        stars = active_creators.sort_values('MoM Growth %', ascending=False).head(10)
        if not stars.empty:
            display_stars = stars[['Last Month GMV', 'Prev Month GMV', 'MoM Growth %', 'Absolute Change']].reset_index()
            display_stars['Last Month GMV'] = display_stars['Last Month GMV'].apply(lambda x: format_inr(x))
            display_stars['Prev Month GMV'] = display_stars['Prev Month GMV'].apply(lambda x: format_inr(x))
            display_stars['Absolute Change'] = display_stars['Absolute Change'].apply(lambda x: format_inr(x))
            display_stars['MoM Growth %'] = display_stars['MoM Growth %'].apply(lambda x: f"+{x*100:.1f}%")
            display_stars = display_stars.rename(columns={'creator_handle': 'Creator'})
            st.dataframe(display_stars, hide_index=True, width="stretch")
        else:
            st.info("No rising stars detected this month.")
            
    with tab_risk:
        risk = active_creators.sort_values('MoM Growth %', ascending=True).head(10)
        risk = risk[risk['MoM Growth %'] < 0] # Only show negative growth
        if not risk.empty:
            display_risk = risk[['Last Month GMV', 'Prev Month GMV', 'MoM Growth %', 'Absolute Change']].reset_index()
            display_risk['Last Month GMV'] = display_risk['Last Month GMV'].apply(lambda x: format_inr(x))
            display_risk['Prev Month GMV'] = display_risk['Prev Month GMV'].apply(lambda x: format_inr(x))
            display_risk['Absolute Change'] = display_risk['Absolute Change'].apply(lambda x: format_inr(x))
            display_risk['MoM Growth %'] = display_risk['MoM Growth %'].apply(lambda x: f"{x*100:.1f}%")
            display_risk = display_risk.rename(columns={'creator_handle': 'Creator'})
            st.dataframe(display_risk, hide_index=True, width="stretch")
        else:
            st.success("No major churn risks detected. All active creators are stable or growing!")
else:
    st.info("Need at least 2 months of historical data to calculate Creator Momentum.")
