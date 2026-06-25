import streamlit as st
import pandas as pd
import datetime
import uuid
from zoneinfo import ZoneInfo
from utils.supabase_client import supabase, fetch_all
from utils.auth import require_auth
from utils.helpers import format_inr

require_auth()

st.set_page_config(page_title="Payout Generation", page_icon="", layout="wide")
st.title("💰 Payout Generation")

IST = ZoneInfo("Asia/Kolkata")
today_ist = datetime.datetime.now(IST).date()

tab_single, tab_history = st.tabs(["👤 Single Creator Payout", "📜 Payout History"])

# ==============================================================================
# TAB 1: SINGLE CREATOR PAYOUT (FLAT STRUCTURE)
# ==============================================================================
with tab_single:
    st.markdown("### 👤 Generate Payout for Specific Creator")
    
    # 1. Fetch Creators
    creators_res = supabase.table('creators').select('id, creator_handle, creator_code, payout_rate').eq('status', 'ACTIVE').order('creator_handle').execute()
    creators_list = creators_res.data or []
    creator_options = {f"{c['creator_handle']} ({c['creator_code']})": c for c in creators_list}
    
    if not creator_options:
        st.warning("No active creators found.")
        st.stop()

    # 2. Inputs at the top level (No nested buttons!)
    col1, col2, col3 = st.columns(3)
    with col1:
        selected_label = st.selectbox("Select Creator", options=list(creator_options.keys()))
    with col2:
        cycle_start = st.date_input("Cycle Start Date", value=today_ist.replace(day=1))
    with col3:
        cycle_end = st.date_input("Cycle End Date", value=today_ist)

    selected_creator = creator_options[selected_label]
    creator_id = selected_creator['id']
    payout_rate = float(selected_creator.get('payout_rate', 89.0))

    # 3. Calculate Dates
    start_dt_ist = datetime.datetime.combine(cycle_start, datetime.time.min, tzinfo=IST)
    end_dt_ist = datetime.datetime.combine(cycle_end, datetime.time.max, tzinfo=IST)
    start_iso = start_dt_ist.astimezone(datetime.timezone.utc).isoformat()
    end_iso = end_dt_ist.astimezone(datetime.timezone.utc).isoformat()

    # 4. Live Calculation (Runs automatically when inputs change)
    with st.spinner("Calculating unsettled earnings..."):
        unsettled_payments = fetch_all(lambda: supabase.table('payments').select(
            'id, amount_inr, fee_inr, tax_inr'
        ).eq('creator_id', creator_id).eq('is_settled', False).gte('created_at', start_iso).lte('created_at', end_iso))
        
        cycle_refunds = fetch_all(lambda: supabase.table('refunds').select('amount_inr, payment_id').gte('created_at', start_iso).lte('created_at', end_iso))
        creator_payment_ids = set(p['payment_id'] for p in fetch_all(lambda: supabase.table('payments').select('payment_id').eq('creator_id', creator_id)))
        creator_refunds = [r for r in cycle_refunds if r.get('payment_id') in creator_payment_ids]

    total_gross = sum(p.get('amount_inr', 0) or 0 for p in unsettled_payments)
    total_fees = sum(p.get('fee_inr', 0) or 0 for p in unsettled_payments)
    total_tax = sum(p.get('tax_inr', 0) or 0 for p in unsettled_payments)
    total_refunds = sum(r.get('amount_inr', 0) or 0 for r in creator_refunds)
    
    adjusted_gross = total_gross - total_refunds
    creator_share = round(adjusted_gross * (payout_rate / 100))
    platform_commission = adjusted_gross - creator_share

    # 5. Show Preview
    st.markdown("### 🧮 Payout Preview")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Unsettled Payments", len(unsettled_payments))
    m2.metric("Gross Amount", format_inr(total_gross))
    m3.metric("Less: Refunds", format_inr(total_refunds))
    m4.metric(f"Creator Share ({payout_rate}%)", format_inr(creator_share))

    if total_gross == 0:
        st.info("📭 No unsettled payments found for this creator in the selected date range.")
    else:
        st.divider()
        st.markdown("### 🔒 Generate & Lock")
        
        # 6. The Generate Button (Top level, no forms inside buttons)
        if st.button("✅ GENERATE PAYOUT NOW", type="primary", width="stretch"):
            try:
                payout_id = str(uuid.uuid4())
                
                # Payload matching EXACT database columns
                payload = {
                    "id": payout_id,
                    "creator_id": creator_id,
                    "cycle_start_date": cycle_start.isoformat(),
                    "cycle_end_date": cycle_end.isoformat(),
                    "gross_amount_inr": total_gross,
                    "razorpay_fees_inr": total_fees,
                    "tax_inr": total_tax,
                    "refunds_deducted_inr": total_refunds,
                    "platform_commission_inr": platform_commission,
                    "creator_share_inr": creator_share,
                    "status": "PENDING",
                    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }
                
                # INSERT
                res = supabase.table('payouts').insert(payload).execute()
                
                # LOCK PAYMENTS
                ids_to_lock = [p['id'] for p in unsettled_payments if 'id' in p]
                if ids_to_lock:
                    for i in range(0, len(ids_to_lock), 100):
                        supabase.table('payments').update({"is_settled": True, "payout_id": payout_id}).in_('id', ids_to_lock[i:i+100]).execute()
                
                st.success(f"🎉 SUCCESS! Payout of {format_inr(creator_share)} generated and locked!")
                st.balloons()
                
                # Force a clean reload
                st.rerun()
                
            except Exception as e:
                # This will now definitely show if there is a DB error
                st.error(f"❌ DATABASE ERROR: {e}")

# ==============================================================================
# TAB 2: HISTORY (Simplified to ensure it loads)
# ==============================================================================
with tab_history:
    st.markdown("### 📜 Payout History")
    
    if st.button("🔄 Refresh Data"):
        st.rerun()

    with st.spinner("Loading..."):
        payouts_data = fetch_all(lambda: supabase.table('payouts').select(
            '*, creators:creator_id(creator_handle, creator_code)'
        ).order('created_at', desc=True))
        
    if not payouts_data:
        st.info("No payouts found.")
    else:
        df = pd.DataFrame(payouts_data)
        
        # Safe mapping
        df['Creator'] = df['creators'].apply(lambda x: f"{x.get('creator_handle', 'Unknown')}" if isinstance(x, dict) else 'Unknown')
        df['Amount'] = df.get('creator_share_inr', pd.Series([0]*len(df))).apply(format_inr)
        df['Status'] = df.get('status', pd.Series(['UNKNOWN']*len(df)))
        df['Ref'] = df.get('transaction_ref', pd.Series(['N/A']*len(df))).fillna('N/A')
        
        def get_cycle(row):
            s, e = row.get('cycle_start_date'), row.get('cycle_end_date')
            if s and e:
                try: return f"{pd.to_datetime(s).strftime('%d %b')} - {pd.to_datetime(e).strftime('%d %b')}"
                except: return "N/A"
            return "N/A"
            
        df['Cycle'] = df.apply(get_cycle, axis=1)
        
        st.dataframe(df[['created_at', 'Creator', 'Cycle', 'Amount', 'Status', 'Ref']], hide_index=True)
