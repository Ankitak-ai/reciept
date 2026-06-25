import streamlit as st
import pandas as pd
import datetime
import uuid
from zoneinfo import ZoneInfo
from utils.supabase_client import supabase, fetch_all
from utils.auth import require_auth
from utils.helpers import format_inr

require_auth()

st.set_page_config(page_title="Payout Generation (Nuclear Debug)", page_icon="💰", layout="wide")
st.title("💰 Payout Generation (Nuclear Debug)")

IST = ZoneInfo("Asia/Kolkata")
today_ist = datetime.datetime.now(IST).date()

# ==============================================================================
# DATE INPUTS
# ==============================================================================
st.markdown("###  Select Payout Cycle")
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
# SINGLE CREATOR PAYOUT (NUCLEAR DEBUG)
# ==============================================================================
st.markdown("###  Generate Payout for Specific Creator")

creators_res = supabase.table('creators').select('id, creator_handle, creator_code, payout_rate').eq('status', 'ACTIVE').order('creator_handle').execute()
creators_list = creators_res.data or []
creator_options = {f"{c['creator_handle']} ({c['creator_code']})": c for c in creators_list}

if not creator_options:
    st.warning("No active creators found.")
    st.stop()

selected_label = st.selectbox("Select Creator", options=list(creator_options.keys()))
selected_creator = creator_options[selected_label]
creator_id = selected_creator['id']
payout_rate = float(selected_creator.get('payout_rate', 89.0))

if st.button(" Calculate & Preview", type="primary"):
    with st.spinner("Calculating..."):
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

    st.markdown("###  Preview")
    st.write(f"**Unsettled Payments Found:** {len(unsettled_payments)}")
    st.write(f"**Gross:** {format_inr(total_gross)} | **Refunds:** {format_inr(total_refunds)}")
    st.write(f"**Creator Share ({payout_rate}%):** {format_inr(creator_share)}")

    if total_gross == 0:
        st.warning(" No unsettled payments found.")
        st.stop()
    else:
        with st.form("generate_form"):
            submitted = st.form_submit_button(" GENERATE PAYOUT (DEBUG)", type="primary", width="stretch")
            
            if submitted:
                payout_id = str(uuid.uuid4())
                
                # 1. Prepare Payload
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
                    # Added timestamps just in case the DB requires them
                    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }
                
                st.markdown("#### 📦 Payload being sent:")
                st.json(payload)
                
                st.markdown("#### 📡 Attempting Database Insert...")
                
                # 2. EXECUTE INSERT (No try/except so we see the raw error if it fails)
                res = supabase.table('payouts').insert(payload).execute()
                
                st.markdown("#### ✅ Insert Response Object:")
                st.write(f"**Data returned:** {res.data}")
                st.write(f"**Count:** {res.count}")
                
                # 3. DIRECT VERIFICATION
                st.markdown("#### 🔍 Direct Database Verification...")
                verify_res = supabase.table('payouts').select('*').eq('id', payout_id).execute()
                
                if verify_res.data:
                    st.success(f"🎉 SUCCESS! The payout IS in the database. ID: {payout_id}")
                    st.write("Raw DB Row:", verify_res.data[0])
                    
                    # 4. LOCK PAYMENTS
                    st.markdown("#### 🔒 Locking Payments...")
                    ids_to_lock = [p['id'] for p in unsettled_payments if 'id' in p]
                    if ids_to_lock:
                        for i in range(0, len(ids_to_lock), 100):
                            chunk = ids_to_lock[i:i+100]
                            supabase.table('payments').update({"is_settled": True, "payout_id": payout_id}).in_('id', chunk).execute()
                        st.success(f"Locked {len(ids_to_lock)} payments.")
                else:
                    st.error("❌ FAILED! The insert returned a response, but the row DOES NOT exist in the database.")
                    st.write("This usually means Row Level Security (RLS) blocked the insert, or a database trigger rejected it.")
                
                st.stop() # Stop here so we can read the results
