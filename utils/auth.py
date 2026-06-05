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
    comparison_date = st.date_input("Comparison Date", value=yesterday_ist_date, help="The day to compare against.")

# Create exact IST boundaries
primary_start_ist = datetime.datetime.combine(primary_date, datetime.time.min, tzinfo=IST)
primary_end_ist = datetime.datetime.combine(primary_date, datetime.time.max, tzinfo=IST)
comparison_start_ist = datetime.datetime.combine(comparison_date, datetime.time.min, tzinfo=IST)
comparison_end_ist = datetime.datetime.combine(comparison_date, datetime.time.max, tzinfo=IST)

# Convert to UTC for Supabase
primary_start_utc = primary_start_ist.astimezone(datetime.timezone.utc).isoformat()
primary_end_utc = primary_end_ist.astimezone(datetime.timezone.utc).isoformat()
comparison_start_utc = comparison_start_ist.astimezone(datetime.timezone.utc).isoformat()
comparison_end_utc = comparison_end_ist.astimezone(datetime.timezone.utc).isoformat()

st.caption(f"🕒 Analyzing: **{primary_date.strftime('%A, %d %B %Y')}** vs **{comparison_date.strftime('%A, %d %B %Y')}** (IST)")

# ==============================================================================
# 2. DATA FETCHING
# ==============================================================================
with st.spinner("Crunching the numbers..."):
    # Primary Date Data
    pay_primary_res = supabase.table('payments').select('amount_inr, fee_inr, tax_inr, created_at').gte('created_at', primary_start_utc).lte('created_at', primary_end_utc).execute()
    pay_primary = pay_primary_res.data or []
    ref_primary_res = supabase.table('refunds').select('amount_inr').gte('created_at', primary_start_utc).lte('created_at', primary_end_utc).execute()
    ref_primary = ref_primary_res.data or []
    new_creators_res = supabase.table('creators').select('id').gte('created_at', primary_start_utc).lte('created_at', primary_end_utc).execute()
    new_creators_primary = len(new_creators_res.data or [])

    # Comparison Date Data
    pay_comp_res = supabase.table('payments').select('amount_inr, fee_inr, tax_inr').gte('created_at', comparison_start_utc).lte('created_at', comparison_end_utc).execute()
    pay_comp = pay_comp_res.data or []
    ref_comp_res = supabase.table('refunds').select('amount_inr').gte('created_at', comparison_start_utc).lte('created_at', comparison_end_utc).execute()
    ref_comp = ref_comp_res.data or []

# ==============================================================================
# 3. CALCULATIONS
# ==============================================================================
primary_gmv = sum(p.get('amount_inr', 0) or 0 for p in pay_primary)
comp_gmv = sum(p.get('amount_inr', 0) or 0 for p in pay_comp)

primary_fees = sum((p.get('fee_inr', 0) or 0) + (p.get('tax_inr', 0) or 0) for p in pay_primary)
comp_fees = sum((p.get('fee_inr', 0) or 0) + (p.get('tax_inr', 0) or 0) for p in pay_comp)

primary_refunds = sum(r.get('amount_inr', 0) or 0 for r in ref_primary)
comp_refunds = sum(r.get('amount_inr', 0) or 0 for r in ref_comp)

primary_txn_count = len(pay_primary)
comp_txn_count = len(pay_comp)

primary_net_rev = primary_gmv - primary_refunds
comp_net_rev = comp_gmv - comp_refunds

# Helper for Delta %
def calc_delta(p_val, c_val):
    if c_val == 0: return "N/A" if p_val == 0 else "+∞"
    return f"{((p_val - c_val) / c_val) * 100:+.1f}%"

delta_gmv = calc_delta(primary_gmv, comp_gmv)
delta_txns = calc_delta(primary_txn_count, comp_txn_count)
delta_fees = calc_delta(primary_fees, comp_fees)
delta_refunds = calc_delta(primary_refunds, comp_refunds)
delta_net_rev = calc_delta(primary_net_rev, comp_net_rev)

peak_hour_str = "No activity on this day"

# ==============================================================================
# 4. UI LAYOUT
# ==============================================================================
tab_metrics, tab_hourly, tab_export = st.tabs(["📊 Executive Summary", "⏰ Hourly Heatmap", "📋 Shareable Report"])

# --- TAB 1: METRICS & COMPARISON TABLE ---
with tab_metrics:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Primary GMV", format_inr(primary_gmv), delta=delta_gmv)
    c2.metric("Transactions", primary_txn_count, delta=delta_txns)
    c3.metric("Gateway Fees", format_inr(primary_fees))
    c4.metric("Refunds", format_inr(primary_refunds), delta_color="inverse" if primary_refunds > 0 else "off")

    st.divider()
    
    # ✨ NEW: EXPLICIT COMPARISON TABLE
    st.markdown(f"#### ⚖️ Side-by-Side Comparison ({primary_date.strftime('%d %b')} vs {comparison_date.strftime('%d %b')})")
    
    comparison_data = {
        "Metric": ["Gross Volume (GMV)", "Net Revenue", "Total Transactions", "Gateway Fees Paid", "Refunds Processed"],
        f"{primary_date.strftime('%d %b')} (Focus)": [
            format_inr(primary_gmv), 
            format_inr(primary_net_rev),
            primary_txn_count, 
            format_inr(primary_fees), 
            format_inr(primary_refunds)
        ],
        f"{comparison_date.strftime('%d %b')} (Base)": [
            format_inr(comp_gmv), 
            format_inr(comp_net_rev),
            comp_txn_count, 
            format_inr(comp_fees), 
            format_inr(comp_refunds)
        ],
        "Change (%)": [delta_gmv, delta_net_rev, delta_txns, delta_fees, delta_refunds]
    }
    
    df_comp = pd.DataFrame(comparison_data)
    st.dataframe(df_comp, hide_index=True, width="stretch")

# --- TAB 2: HOURLY HEATMAP ---
with tab_hourly:
    st.markdown(f"### ⏰ Transaction Volume by Hour ({primary_date.strftime('%d %b %Y')} IST)")
    
    if pay_primary:
        df_hourly = pd.DataFrame(pay_primary)
        df_hourly['ist_hour'] = pd.to_datetime(df_hourly['created_at']).dt.tz_convert(IST).dt.hour
        hourly_counts = df_hourly.groupby('ist_hour').size().reset_index(name='count')
        
        all_hours = pd.DataFrame({'ist_hour': range(24)})
        hourly_counts = pd.merge(all_hours, hourly_counts, on='ist_hour', how='left').fillna(0)
        
        if hourly_counts['count'].max() > 0:
            max_idx = hourly_counts['count'].idxmax()
            peak_hr = int(hourly_counts.loc[max_idx, 'ist_hour'])
            peak_txns = int(hourly_counts.loc[max_idx, 'count'])
            peak_hour_str = f"{peak_hr:02d}:00 IST ({peak_txns} txns)"
        
        fig = px.bar(hourly_counts, x='ist_hour', y='count', labels={'ist_hour': 'Hour of Day (IST)', 'count': 'Donations'}, color='count', color_continuous_scale='blues')
        fig.update_layout(xaxis=dict(dtick=1))
        st.plotly_chart(fig, width="stretch")
    else:
        st.info(f"No transactions recorded on {primary_date}.")

# --- TAB 3: SHAREABLE REPORT ---
with tab_export:
    st.markdown("### 📋 Shareable Performance Report")
    st.caption("Copy this formatted text and paste it directly into WhatsApp, Slack, or Email.")
    
    eod_text = f"""
📊 *StreamHeart Performance Report*
🗓 *Focus:* {primary_date.strftime('%d %b %Y')} | ⚖️ *Base:* {comparison_date.strftime('%d %b %Y')}

💰 *FINANCIALS*
• Gross Volume: {format_inr(primary_gmv)} (vs {format_inr(comp_gmv)} | {delta_gmv})
• Net Revenue: {format_inr(primary_net_rev)} (vs {format_inr(comp_net_rev)} | {delta_net_rev})
• Gateway Fees: {format_inr(primary_fees)} (vs {format_inr(comp_fees)})
• Refunds: {format_inr(primary_refunds)} (vs {format_inr(comp_refunds)})

🧾 *OPERATIONS*
• Transactions: {primary_txn_count} (vs {comp_txn_count} | {delta_txns})
• New Creators: {new_creators_primary}

⏰ *PEAK ACTIVITY*
• Highest Volume Hour: {peak_hour_str}

_Generated by StreamHeart Finance Infrastructure._
    """
    
    st.text_area("Report Text (Click inside to copy)", eod_text, height=350)
    
    st.download_button(
        label="⬇️ Download as .txt",
        data=eod_text,
        file_name=f"StreamHeart_Report_{primary_date.strftime('%Y-%m-%d')}.txt",
        mime="text/plain",
        width="stretch"
    )
