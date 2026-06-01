import streamlit as st
import pandas as pd
import datetime
from utils.supabase_client import supabase

st.set_page_config(page_title="Payout Management", page_icon="💰", layout="wide")
st.title("💰 Payout Generation & Reconciliation")

# Helper function for currency formatting
def format_inr(val):
    if val is None or val == 0: return "₹0.00"
    try: return f"₹{float(val)/100:.2f}"
    except (ValueError, TypeError): return "₹0.00"

# ==============================================================================
# TABS SETUP
# ==============================================================================
tab_generate, tab_history = st.tabs(["🚀 Generate New Payout", "📜 Payout History & Reconciliation"])

# ==============================================================================
# TAB 1: GENERATE NEW PAYOUT
# ==============================================================================
with tab_generate:
    st.markdown("### 📅 Select Payout Cycle")
    col1, col2, col3 = st.columns(3)
    
    # Default to last month
    today = datetime.date.today()
    first_day_last_month = today.replace(day=1) - datetime.timedelta(days=1)
    default_start = first_day_last_month.replace(day=1)
    default_end = first_day_last_month

    with col1:
        start_date = st.date_input("Cycle Start Date", value=default_start)
    with col2:
        end_date = st.date_input("Cycle End Date", value=default_end)
    with col3:
        # Fetch creators for dropdown
        creators_res = supabase.table('creators').select('id, creator_handle, creator_code, payout_rate').eq('status', 'ACTIVE').order('creator_handle').execute()
        creators_list = creators_res.data or []
        
        creator_options = {"All Creators (Bulk)": "ALL"}
        for c in creators_list:
            creator_options[f"{c['creator_handle']} ({c['creator_code']})"] = c['id']
            
        selected_creator_label = st.selectbox("Select Creator", options=list(creator_options.keys()))
        selected_creator_id = creator_options[selected_creator_label]

    # Convert dates to ISO strings for Supabase (End date needs to include the whole day)
    start_iso = f"{start_date}T00:00:00+00:00"
    end_iso = f"{end_date}T23:59:59+00:00"

    # --- PREVIEW LOGIC ---
    if st.button("🔍 Preview Payout Calculation", type="secondary", width="stretch"):
        with st.spinner("Calculating unsettled payments and refunds..."):
            
            preview_data = []
            
            # Determine which creators to process
            target_creators = creators_list if selected_creator_id == "ALL" else [next(c for c in creators_list if c['id'] == selected_creator_id)]
            
            for creator in target_creators:
                cid = creator['id']
                rate = float(creator.get('payout_rate', 89.0))
                
                # 1. Fetch UNSETTLED payments for this cycle
                payments_res = supabase.table('payments').select('amount_inr, fee_inr, tax_inr')\
                    .eq('creator_id', cid)\
                    .eq('is_settled', False)\
                    .gte('created_at', start_iso)\
                    .lte('created_at', end_iso).execute()
                
                payments = payments_res.data or []
                if not payments: continue # Skip creators with 0 activity
                
                gross = sum(p.get('amount_inr', 0) or 0 for p in payments)
                fees = sum(p.get('fee_inr', 0) or 0 for p in payments)
                tax = sum(p.get('tax_inr', 0) or 0 for p in payments)
                
                # 2. Fetch refunds for this cycle (deducted from current cycle regardless of original payment date)
                refunds_res = supabase.table('refunds').select('amount_inr')\
                    .eq('creator_id', cid)\
                    .gte('created_at', start_iso)\
                    .lte('created_at', end_iso).execute()
                
                refunds = refunds_res.data or []
                total_refunded = sum(r.get('amount_inr', 0) or 0 for r in refunds)
                
                # 3. Calculate Final Math
                net_base = gross - fees - tax
                final_net = net_base - total_refunded
                creator_share = round(final_net * (rate / 100))
                platform_comm = final_net - creator_share
                
                preview_data.append({
                    "Creator": creator['creator_handle'],
                    "Code": creator['creator_code'],
                    "Rate": f"{rate}%",
                    "Txns": len(payments),
                    "Gross (INR)": format_inr(gross),
                    "Fees (INR)": format_inr(fees),
                    "Refunds (INR)": format_inr(total_refunded),
                    "Net Base (INR)": format_inr(net_base),
                    "Creator Payout (INR)": format_inr(creator_share),
                    "Platform Cut (INR)": format_inr(platform_comm),
                    # Store raw integers for the commit phase
                    "_gross": gross, "_fees": fees, "_tax": tax, "_refunded": total_refunded,
                    "_net_base": net_base, "_final_net": final_net, 
                    "_creator_share": creator_share, "_platform_comm": platform_comm,
                    "_rate": rate, "_cid": cid
                })
            
            if not preview_data:
                st.warning("📭 No unsettled payments found for the selected criteria.")
                st.session_state.pop('payout_preview', None)
            else:
                st.session_state['payout_preview'] = preview_data
                st.rerun()

    # --- DISPLAY PREVIEW & COMMIT ---
    if 'payout_preview' in st.session_state and st.session_state['payout_preview']:
        st.markdown("---")
        st.markdown("### 📊 Payout Preview")
        st.info("⚠️ **Warning:** Clicking 'Generate & Lock Payouts' will permanently mark these transactions as settled. They will not be included in future payout cycles.")
        
        df_preview = pd.DataFrame(st.session_state['payout_preview'])
        
        # Display clean dataframe (drop hidden raw columns)
        display_cols = [c for c in df_preview.columns if not c.startswith('_')]
        st.dataframe(df_preview[display_cols], width="stretch", hide_index=True)
        
        # Total Summary
        total_payout_out = sum(row['_creator_share'] for row in st.session_state['payout_preview'])
        total_platform_in = sum(row['_platform_comm'] for row in st.session_state['payout_preview'])
        
        col_sum1, col_sum2 = st.columns(2)
        col_sum1.metric("💸 Total to Pay Creators", format_inr(total_payout_out))
        col_sum2.metric("🏦 Total Platform Revenue", format_inr(total_platform_in))
        
        if st.button("🔒 Generate & Lock Payouts", type="primary", width="stretch"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            total_steps = len(st.session_state['payout_preview'])
            
            success_count = 0
            for idx, row in enumerate(st.session_state['payout_preview']):
                status_text.text(f"Processing payout for {row['Creator']}...")
                
                try:
                    # 1. Insert locked record into 'payouts' table
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
                    
                    # 2. Mark underlying payments as settled
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
    
    # Fetch all payouts with creator details
    payouts_res = supabase.table('payouts').select(
        '*, creators:creator_id(creator_handle, creator_code)'
    ).order('created_at', desc=True).execute()
    
    if not payouts_res.data:
        st.info("No payouts have been generated yet.")
    else:
        df_payouts = pd.DataFrame(payouts_res.data)
        
        # Format Data
        df_payouts['Creator'] = df_payouts['creators'].apply(lambda x: x['creator_handle'] if x else 'Unknown')
        df_payouts['Code'] = df_payouts['creators'].apply(lambda x: x['creator_code'] if x else 'Unknown')
        df_payouts['Gross'] = df_payouts['gross_amount_inr'].apply(format_inr)
        df_payouts['Fees'] = df_payouts['razorpay_fees_inr'].apply(format_inr)
        df_payouts['Refunds'] = df_payouts['refunds_deducted_inr'].apply(format_inr)
        df_payouts['Net Payout'] = df_payouts['creator_share_inr'].apply(format_inr)
        df_payouts['Platform Cut'] = df_payouts['platform_commission_inr'].apply(format_inr)
        
        # Display Table
        display_payouts = df_payouts[[
            'created_at', 'Creator', 'Code', 'cycle_start_date', 'cycle_end_date', 
            'status', 'Gross', 'Fees', 'Refunds', 'Net Payout', 'Platform Cut', 'transaction_ref'
        ]].rename(columns={
            'created_at': 'Generated On',
            'cycle_start_date': 'Cycle Start',
            'cycle_end_date': 'Cycle End',
            'transaction_ref': 'Bank UTR / Ref'
        })
        
        st.dataframe(display_payouts, width="stretch", hide_index=True)
        
        st.divider()
        
        # --- UPDATE PAYOUT STATUS (RECONCILIATION) ---
        st.markdown("### 🏦 Mark Payout as PAID")
        st.caption("Once the bank transfer is complete, update the status and enter the transaction reference for audit purposes.")
        
        # Create a clean list for the dropdown
        pending_payouts = df_payouts[df_payouts['status'] != 'PAID']
        
        if pending_payouts.empty:
            st.success("🎉 All generated payouts have been marked as PAID!")
        else:
            payout_options = {
                f"{row['Creator']} | {row['cycle_start_date']} to {row['cycle_end_date']} | {row['Net Payout']}": row['id'] 
                for _, row in pending_payouts.iterrows()
            }
            
            with st.form("mark_paid_form"):
                col_a, col_b = st.columns([2, 1])
                with col_a:
                    selected_payout_label = st.selectbox("Select Payout to Mark as Paid", options=list(payout_options.keys()))
                    utr_ref = st.text_input("Bank UTR / Transaction Reference", placeholder="e.g., UTTR123456789")
                with col_b:
                    st.write("") # Spacing
                    st.write("") # Spacing
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
