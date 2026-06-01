import streamlit as st
import pandas as pd
import datetime
from utils.supabase_client import supabase
from utils.helpers import format_inr, to_ist, IST

st.set_page_config(page_title="Payout Management", page_icon="💰", layout="wide")
st.title("💰 Payout Generation & Reconciliation")

# ==============================================================================
# TABS SETUP
# ==============================================================================
tab_generate, tab_history = st.tabs(["🚀 Generate New Payout", "📜 Payout History & Reconciliation"])

# ==============================================================================
# TAB 1: GENERATE NEW PAYOUT
# ==============================================================================
with tab_generate:
    st.markdown("### 📅 Select Payout Cycle (All dates calculated in IST)")
    col1, col2, col3 = st.columns(3)
    
    today = datetime.date.today()
    first_day_last_month = today.replace(day=1) - datetime.timedelta(days=1)
    default_start = first_day_last_month.replace(day=1)
    default_end = first_day_last_month

    with col1:
        start_date = st.date_input("Cycle Start Date", value=default_start)
    with col2:
        end_date = st.date_input("Cycle End Date", value=default_end)
    with col3:
        creators_res = supabase.table('creators').select('id, creator_handle, creator_code, payout_rate').eq('status', 'ACTIVE').order('creator_handle').execute()
        creators_list = creators_res.data or []
        
        creator_options = {"All Creators (Bulk)": "ALL"}
        for c in creators_list:
            creator_options[f"{c['creator_handle']} ({c['creator_code']})"] = c['id']
            
        selected_creator_label = st.selectbox("Select Creator", options=list(creator_options.keys()))
        selected_creator_id = creator_options[selected_creator_label]

    # IST BOUNDARY CALCULATION
    start_dt_ist = datetime.datetime.combine(start_date, datetime.time.min, tzinfo=IST)
    end_dt_ist = datetime.datetime.combine(end_date, datetime.time.max, tzinfo=IST)
    start_iso = start_dt_ist.astimezone(datetime.timezone.utc).isoformat()
    end_iso = end_dt_ist.astimezone(datetime.timezone.utc).isoformat()
    
    st.caption(f"🕒 Querying from: `{to_ist(start_iso)}` to `{to_ist(end_iso)}`")

    if st.button("🔍 Preview Payout Calculation", type="secondary", width="stretch"):
        with st.spinner("Calculating unsettled payments and refunds..."):
            preview_data = []
            target_creators = creators_list if selected_creator_id == "ALL" else [next(c for c in creators_list if c['id'] == selected_creator_id)]
            
            for creator in target_creators:
                cid = creator['id']
                rate = float(creator.get('payout_rate', 89.0))
                
                payments_res = supabase.table('payments').select('amount_inr, fee_inr, tax_inr')\
                    .eq('creator_id', cid)\
                    .eq('is_settled', False)\
                    .gte('created_at', start_iso)\
                    .lte('created_at', end_iso).execute()
                
                payments = payments_res.data or []
                if not payments: continue 
                
                gross = sum(p.get('amount_inr', 0) or 0 for p in payments)
                fees = sum(p.get('fee_inr', 0) or 0 for p in payments)
                tax = sum(p.get('tax_inr', 0) or 0 for p in payments)
                
                refunds_res = supabase.table('refunds').select('amount_inr')\
                    .eq('creator_id', cid)\
                    .gte('created_at', start_iso)\
                    .lte('created_at', end_iso).execute()
                
                refunds = refunds_res.data or []
                total_refunded = sum(r.get('amount_inr', 0) or 0 for r in refunds)
                
                # ==========================================
                # GROSS-BASED PAYOUT MATH (Platform absorbs fees)
                # ==========================================
                adjusted_gross = gross - total_refunded
                creator_share = round(adjusted_gross * (rate / 100))
                platform_commission = adjusted_gross - creator_share
                platform_net_profit = platform_commission - fees - tax
                
                preview_data.append({
                    "Creator": creator['creator_handle'],
                    "Code": creator['creator_code'],
                    "Rate": f"{rate}%",
                    "Txns": len(payments),
                    "Gross (INR)": format_inr(gross),
                    "Refunds (INR)": format_inr(total_refunded),
                    "Creator Payout (INR)": format_inr(creator_share),
                    "Platform Comm. (INR)": format_inr(platform_commission),
                    "Razorpay Cuts (INR)": format_inr(fees + tax),
                    "Platform Net Profit": format_inr(platform_net_profit),
                    # Raw integers for DB commit
                    "_gross": gross, "_fees": fees, "_tax": tax, "_refunded": total_refunded,
                    "_creator_share": creator_share, "_platform_comm": platform_commission,
                    "_cid": cid
                })
            
            if not preview_data:
                st.warning("📭 No unsettled payments found for the selected IST date range.")
                st.session_state.pop('payout_preview', None)
            else:
                st.session_state['payout_preview'] = preview_data
                st.rerun()

    if 'payout_preview' in st.session_state and st.session_state['payout_preview']:
        st.markdown("---")
        st.markdown("### 📊 Payout Preview")
        st.info("⚠️ **Warning:** Clicking 'Generate & Lock Payouts' will permanently mark these transactions as settled.")
        
        df_preview = pd.DataFrame(st.session_state['payout_preview'])
        display_cols = [c for c in df_preview.columns if not c.startswith('_')]
        st.dataframe(df_preview[display_cols], width="stretch", hide_index=True)
        
        total_payout_out = sum(row['_creator_share'] for row in st.session_state['payout_preview'])
        total_platform_in = sum(row['_platform_comm'] for row in st.session_state['payout_preview'])
        
        col_sum1, col_sum2 = st.columns(2)
        col_sum1.metric("💸 Total to Pay Creators", format_inr(total_payout_out))
        col_sum2.metric("🏦 Total Platform Commission", format_inr(total_platform_in))
        
        if st.button("🔒 Generate & Lock Payouts", type="primary", width="stretch"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            total_steps = len(st.session_state['payout_preview'])
            success_count = 0
            
            for idx, row in enumerate(st.session_state['payout_preview']):
                status_text.text(f"Processing payout for {row['Creator']}...")
                try:
                    payout_insert = {
                        "creator_id": row['_cid'],
                        "cycle_start_date": start_date.isoformat(),
                        "cycle_end_date": end_date.isoformat(),
                        "gross_amount_inr": row['_gross'],
                        "razorpay_fees_inr": row['_fees'],
                        "tax_inr": row['_tax'],
                        "refunds_deducted_inr": row['_refunded'],
                        "platform_commission_inr": row['_platform_comm'],
                        "creator_share_inr": row['_creator_share'],
                        "status": "PENDING"
                    }
                    
                    new_payout_res = supabase.table('payouts').insert(payout_insert).execute()
                    new_payout_id = new_payout_res.data[0]['id']
                    
                    supabase.table('payments').update({
                        "is_settled": True,
                        "payout_id": new_payout_id
                    }).eq('creator_id', row['_cid'])\
                      .eq('is_settled', False)\
                      .gte('created_at', start_iso)\
                      .lte('created_at', end_iso).execute()
                      
                    success_count += 1
                except Exception as e:
                    st.error(f"Failed to generate payout for {row['Creator']}: {e}")
                
                progress_bar.progress((idx + 1) / total_steps)
            
            status_text.text("")
            progress_bar.empty()
            st.success(f"✅ Successfully generated and locked {success_count} payout records!")
            st.session_state.pop('payout_preview', None)
            st.rerun()

# ==============================================================================
# TAB 2: PAYOUT HISTORY & RECONCILIATION
# ==============================================================================
with tab_history:
    st.markdown("### 📜 Generated Payouts Ledger")
    
    payouts_res = supabase.table('payouts').select(
        '*, creators:creator_id(creator_handle, creator_code)'
    ).order('created_at', desc=True).execute()
    
    if not payouts_res.data:
        st.info("No payouts have been generated yet.")
    else:
        df_payouts = pd.DataFrame(payouts_res.data)
        
        df_payouts['Creator'] = df_payouts['creators'].apply(lambda x: x['creator_handle'] if x else 'Unknown')
        df_payouts['Code'] = df_payouts['creators'].apply(lambda x: x['creator_code'] if x else 'Unknown')
        df_payouts['Gross'] = df_payouts['gross_amount_inr'].apply(format_inr)
        df_payouts['Refunds'] = df_payouts['refunds_deducted_inr'].apply(format_inr)
        df_payouts['Creator Payout'] = df_payouts['creator_share_inr'].apply(format_inr)
        df_payouts['Platform Comm.'] = df_payouts['platform_commission_inr'].apply(format_inr)
        df_payouts['Generated On'] = df_payouts['created_at'].apply(to_ist)
        
        display_payouts = df_payouts[[
            'Generated On', 'Creator', 'Code', 'cycle_start_date', 'cycle_end_date', 
            'status', 'Gross', 'Refunds', 'Creator Payout', 'Platform Comm.', 'transaction_ref'
        ]]
        
        st.dataframe(display_payouts, width="stretch", hide_index=True)
        
        st.divider()
        st.markdown("### 🏦 Mark Payout as PAID")
        st.caption("Once the bank transfer is complete, update the status and enter the transaction reference.")
        
        pending_payouts = df_payouts[df_payouts['status'] != 'PAID']
        
        if pending_payouts.empty:
            st.success("🎉 All generated payouts have been marked as PAID!")
        else:
            payout_options = {
                f"{row['Creator']} | {row['cycle_start_date']} to {row['cycle_end_date']} | {row['Creator Payout']}": row['id'] 
                for _, row in pending_payouts.iterrows()
            }
            
            with st.form("mark_paid_form"):
                col_a, col_b = st.columns([2, 1])
                with col_a:
                    selected_payout_label = st.selectbox("Select Payout to Mark as Paid", options=list(payout_options.keys()))
                    utr_ref = st.text_input("Bank UTR / Transaction Reference", placeholder="e.g., UTTR123456789")
                with col_b:
                    st.write("") 
                    st.write("") 
                    submitted_paid = st.form_submit_button("Mark as PAID", type="primary", width="stretch")
                
                if submitted_paid:
                    payout_id = payout_options[selected_payout_label]
                    try:
                        supabase.table('payouts').update({
                            "status": "PAID",
                            "transaction_ref": utr_ref,
                            "payout_date": datetime.datetime.now(datetime.timezone.utc).isoformat()
                        }).eq('id', payout_id).execute()
                        st.success("✅ Payout marked as PAID successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to update status: {e}")
