import streamlit as st
import pandas as pd
import datetime
import uuid
from zoneinfo import ZoneInfo
from utils.supabase_client import supabase, fetch_all
from utils.auth import require_auth
from utils.helpers import format_inr

require_auth()

st.set_page_config(page_title="Payout Generation (Debug)", page_icon="💰", layout="wide")
st.title("💰 Payout Generation (Debug Mode)")

IST = ZoneInfo("Asia/Kolkata")
today_ist = datetime.datetime.now(IST).date()

# ==============================================================================
# DATE INPUTS
# ==============================================================================
st.markdown("### 📅 Select Payout Cycle")
col1, col2 = st.columns(2)
with col1:
    cycle_start = st.date_input("Cycle Start Date", value=today_ist.replace(day=1))
with col2:
    cycle_end = st.date_input("Cycle End Date", value=today_ist)

start_dt_ist = datetime.datetime.combine(cycle_start, datetime.time.min, tzinfo=IST)
end_dt_ist = datetime.datetime.combine(cycle_end, datetime.time.max, tzinfo=IST)
start_iso = start_dt_ist.astimezone(datetime.timezone.utc).isoformat()
end_iso = end_dt_ist.astimezone(datetime.timezone.utc).isoformat()

# ==============================================================================
# SINGLE CREATOR PAYOUT (WITH DEBUGGING)
# ==============================================================================
st.markdown("### 👤 Generate Payout for Specific Creator")

creators_res = supabase.table('creators').select('id, creator_handle, creator_code, payout_rate').eq('status', 'ACTIVE').order('creator_handle').execute()
creators_list = creators_res.data or []
creator_options = {f"{c['creator_handle']} ({c['creator_code']})": c for c in creators_list}

if not creator_options:
    st.warning("No active creators found.")
else:
    selected_label = st.selectbox("Select Creator", options=list(creator_options.keys()))
    selected_creator = creator_options[selected_label]
    creator_id = selected_creator['id']
    payout_rate = float(selected_creator.get('payout_rate', 89.0))

    if st.button("🔍 Calculate & Preview", type="primary"):
        with st.spinner("Calculating..."):
            # 1. Fetch Unsettled Payments
            unsettled_payments = fetch_all(lambda: supabase.table('payments').select(
                'id, amount_inr, fee_inr, tax_inr'
            ).eq('creator_id', creator_id).eq('is_settled', False).gte('created_at', start_iso).lte('created_at', end_iso))
            
            # 2. Fetch Refunds
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

        st.markdown("### 🧮 Preview")
        st.write(f"**Unsettled Payments Found:** {len(unsettled_payments)}")
        st.write(f"**Gross:** {format_inr(total_gross)} | **Refunds:** {format_inr(total_refunds)}")
        st.write(f"**Creator Share ({payout_rate}%):** {format_inr(creator_share)}")

        if total_gross == 0:
            st.warning("📭 No unsettled payments found. (Check if they are already marked as 'is_settled = True')")
        else:
            with st.form("generate_form"):
                submitted = st.form_submit_button("🔒 GENERATE PAYOUT", type="primary", width="stretch")
                
                if submitted:
                    try:
                        payout_id = str(uuid.uuid4())
                        
                        # DEBUG: Print exactly what we are sending to the database
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
                            "status": "PENDING"
                        }
                        
                        st.json(payload) # Show the exact data being sent
                        st.info("Attempting to insert into 'payouts' table...")

                        # INSERT INTO DATABASE
                        res = supabase.table('payouts').insert(payload).execute()
                        
                        st.success(f"✅ Database Insert Successful! Response: {res}")

                        # LOCK PAYMENTS
                        ids_to_lock = [p['id'] for p in unsettled_payments if 'id' in p]
                        if ids_to_lock:
                            st.info(f"Locking {len(ids_to_lock)} payments...")
                            for i in range(0, len(ids_to_lock), 100):
                                supabase.table('payments').update({"is_settled": True, "payout_id": payout_id}).in_('id', ids_to_lock[i:i+100]).execute()
                        
                        st.balloons()
                        st.success("🎉 Payout Generated and Payments Locked!")
                        st.rerun()

                    except Exception as e:
                        st.error(f" FAILED TO GENERATE: {e}")
