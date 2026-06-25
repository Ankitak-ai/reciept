import streamlit as st
import pandas as pd
import datetime
import uuid
import io
from zoneinfo import ZoneInfo
from collections import defaultdict
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from utils.supabase_client import supabase, fetch_all
from utils.auth import require_auth
from utils.helpers import format_inr

require_auth()

st.set_page_config(page_title="Payout Generation", page_icon="💰", layout="wide")
st.title("💰 Payout Generation & Reconciliation")
st.caption("Calculate creator earnings, lock payout records, and generate official PDF receipts.")

IST = ZoneInfo("Asia/Kolkata")
today_ist = datetime.datetime.now(IST).date()

tab_single, tab_bulk, tab_history = st.tabs([
    " Single Creator Payout", 
    "⚡ Bulk Payouts (All Creators)", 
    "📜 Payout History & Reconciliation"
])

# ==============================================================================
# PDF RECEIPT GENERATOR HELPER
# ==============================================================================
def generate_payout_pdf(payout, creator, fin_info):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    p.setFont("Helvetica-Bold", 20)
    p.drawString(50, height - 50, "StreamHeart Private Limited")
    p.setFont("Helvetica", 12)
    p.drawString(50, height - 70, "Official Payout Receipt")
    
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, height - 120, f"Creator: {creator.get('creator_handle', 'N/A')}")
    p.drawString(50, height - 140, f"Payout ID: {payout.get('id', 'N/A')[:8]}...")
    p.drawString(50, height - 160, f"Generated: {pd.to_datetime(payout.get('created_at')).strftime('%d %b %Y') if payout.get('created_at') else 'N/A'}")
    
    p.setFont("Helvetica", 12)
    y = height - 200
    start_str = pd.to_datetime(payout.get('cycle_start_date')).strftime('%d %b') if payout.get('cycle_start_date') else 'N/A'
    end_str = pd.to_datetime(payout.get('cycle_end_date')).strftime('%d %b') if payout.get('cycle_end_date') else 'N/A'
    p.drawString(50, y, f"Cycle: {start_str} to {end_str}")
    y -= 25
    p.drawString(50, y, f"Gross Volume: {format_inr(payout.get('gross_amount_inr', 0))}")
    y -= 20
    p.drawString(50, y, f"Razorpay Fees: {format_inr(payout.get('razorpay_fees_inr', 0))}")
    y -= 20
    p.drawString(50, y, f"Refunds Deducted: {format_inr(payout.get('refunds_deducted_inr', 0))}")
    y -= 20
    p.drawString(50, y, f"Platform Commission: {format_inr(payout.get('platform_commission_inr', 0))}")
    
    p.setFont("Helvetica-Bold", 16)
    y -= 40
    p.drawString(50, y, f"NET PAYOUT TRANSFERRED: {format_inr(payout.get('creator_share_inr', 0))}")
    
    if fin_info:
        y -= 50
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y, "Remitted To:")
        p.setFont("Helvetica", 10)
        y -= 20
        p.drawString(50, y, f"Name: {fin_info.get('legal_name') or 'N/A'}")
        y -= 15
        p.drawString(50, y, f"UPI: {fin_info.get('upi_id') or 'N/A'}")
        y -= 15
        p.drawString(50, y, f"Bank: {fin_info.get('bank_name') or 'N/A'} (A/C: XXXX{fin_info.get('account_number_last4') or 'N/A'})")
        
    if payout.get('transaction_ref'):
        y -= 40
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y, f"Transaction Ref: {payout['transaction_ref']}")
        y -= 20
        paid_date = pd.to_datetime(payout['payout_date']).strftime('%d %b %Y %H:%M') if payout.get('payout_date') else 'N/A'
        p.drawString(50, y, f"Paid On: {paid_date}")
        
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer.read()

# ==============================================================================
# HELPER: Calculate payout for a specific creator
# ==============================================================================
def calculate_creator_payout(creator_id, payout_rate, start_iso, end_iso):
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

    return {
        "unsettled_payments": unsettled_payments,
        "total_gross": total_gross,
        "total_fees": total_fees,
        "total_tax": total_tax,
        "total_refunds": total_refunds,
        "adjusted_gross": adjusted_gross,
        "creator_share": creator_share,
        "platform_commission": platform_commission
    }

# ==============================================================================
# SHARED DATE INPUTS (Used by Single and Bulk tabs)
# ==============================================================================
# We put these inside the tabs to avoid layout issues, but logic is identical.

# ==============================================================================
# TAB 1: SINGLE CREATOR PAYOUT
# ==============================================================================
with tab_single:
    st.markdown("### 👤 Generate Payout for Specific Creator")
    
    creators_res = supabase.table('creators').select('id, creator_handle, creator_code, payout_rate').eq('status', 'ACTIVE').order('creator_handle').execute()
    creators_list = creators_res.data or []
    creator_options = {f"{c['creator_handle']} ({c['creator_code']})": c for c in creators_list}
    
    if not creator_options:
        st.warning("No active creators found.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            selected_label = st.selectbox("Select Creator", options=list(creator_options.keys()), key="single_sel")
        with col2:
            cycle_start = st.date_input("Cycle Start Date", value=today_ist.replace(day=1), key="single_start")
        with col3:
            cycle_end = st.date_input("Cycle End Date", value=today_ist, key="single_end")

        selected_creator = creator_options[selected_label]
        creator_id = selected_creator['id']
        payout_rate = float(selected_creator.get('payout_rate', 89.0))
        
        # Fetch Bank Details
        fin_res = supabase.table('creator_financial_info').select('*').eq('creator_id', creator_id).execute()
        fin_info = fin_res.data[0] if fin_res.data else {}
        st.info(f"🏦 **Verify Bank Details:** {fin_info.get('legal_name') or 'N/A'} | UPI: {fin_info.get('upi_id') or 'N/A'} | Bank: {fin_info.get('bank_name') or 'N/A'}")

        start_dt_ist = datetime.datetime.combine(cycle_start, datetime.time.min, tzinfo=IST)
        end_dt_ist = datetime.datetime.combine(cycle_end, datetime.time.max, tzinfo=IST)
        start_iso = start_dt_ist.astimezone(datetime.timezone.utc).isoformat()
        end_iso = end_dt_ist.astimezone(datetime.timezone.utc).isoformat()

        with st.spinner("Calculating unsettled earnings..."):
            result = calculate_creator_payout(creator_id, payout_rate, start_iso, end_iso)

        st.markdown("### 🧮 Payout Preview")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Unsettled Payments", len(result['unsettled_payments']))
        m2.metric("Gross Amount", format_inr(result['total_gross']))
        m3.metric("Less: Refunds", format_inr(result['total_refunds']))
        m4.metric(f"Creator Share ({payout_rate}%)", format_inr(result['creator_share']))
        m5.metric("Platform Commission", format_inr(result['platform_commission']))

        if result['total_gross'] == 0:
            st.info("📭 No unsettled payments found for this creator in the selected date range.")
        else:
            st.divider()
            if st.button("✅ GENERATE PAYOUT NOW", type="primary", width="stretch"):
                try:
                    payout_id = str(uuid.uuid4())
                    
                    payload = {
                        "id": payout_id,
                        "creator_id": creator_id,
                        "cycle_start_date": cycle_start.isoformat(),
                        "cycle_end_date": cycle_end.isoformat(),
                        "gross_amount_inr": result['total_gross'],
                        "razorpay_fees_inr": result['total_fees'],
                        "tax_inr": result['total_tax'],
                        "refunds_deducted_inr": result['total_refunds'],
                        "platform_commission_inr": result['platform_commission'],
                        "creator_share_inr": result['creator_share'],
                        "status": "PENDING",
                        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                    }
                    
                    supabase.table('payouts').insert(payload).execute()
                    
                    ids_to_lock = [p['id'] for p in result['unsettled_payments'] if 'id' in p]
                    if ids_to_lock:
                        for i in range(0, len(ids_to_lock), 100):
                            supabase.table('payments').update({"is_settled": True, "payout_id": payout_id}).in_('id', ids_to_lock[i:i+100]).execute()
                    
                    st.success(f"🎉 SUCCESS! Payout of {format_inr(result['creator_share'])} generated and locked!")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ DATABASE ERROR: {e}")

# ==============================================================================
# TAB 2: BULK PAYOUTS (ALL CREATORS)
# ==============================================================================
with tab_bulk:
    st.markdown("### ⚡ Generate Payouts for ALL Active Creators")
    st.caption("This will calculate unsettled earnings for every active creator in the selected cycle.")
    
    col1, col2 = st.columns(2)
    with col1:
        bulk_start = st.date_input("Cycle Start Date", value=today_ist.replace(day=1), key="bulk_start")
    with col2:
        bulk_end = st.date_input("Cycle End Date", value=today_ist, key="bulk_end")

    st.warning("⚠️ **Warning:** This action cannot be easily undone. Ensure the date range is correct before proceeding.")
    
    if st.button("🚀 Run Bulk Payout Generation", type="primary", width="stretch"):
        start_dt_ist = datetime.datetime.combine(bulk_start, datetime.time.min, tzinfo=IST)
        end_dt_ist = datetime.datetime.combine(bulk_end, datetime.time.max, tzinfo=IST)
        start_iso = start_dt_ist.astimezone(datetime.timezone.utc).isoformat()
        end_iso = end_dt_ist.astimezone(datetime.timezone.utc).isoformat()

        with st.spinner("Fetching all unsettled data for bulk processing..."):
            all_unsettled = fetch_all(lambda: supabase.table('payments').select(
                'id, creator_id, amount_inr, fee_inr, tax_inr'
            ).eq('is_settled', False).gte('created_at', start_iso).lte('created_at', end_iso))
            
            all_creators = {c['id']: c for c in fetch_all(lambda: supabase.table('creators').select('id, creator_handle, creator_code, payout_rate').eq('status', 'ACTIVE'))}
            
            creator_payments = defaultdict(list)
            for p in all_unsettled:
                if p.get('creator_id'):
                    creator_payments[p['creator_id']].append(p)

        st.divider()
        st.markdown(f"### 📊 Found **{len(creator_payments)}** creators with unsettled payments.")
        
        if st.button("✅ Confirm & Execute Bulk Payouts", type="primary", width="stretch"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            total_processed = 0
            total_amount = 0
            creator_list = list(creator_payments.keys())
            
            for idx, c_id in enumerate(creator_list):
                status_text.info(f"Processing creator {idx + 1} of {len(creator_list)}...")
                creator = all_creators.get(c_id, {})
                payout_rate = float(creator.get('payout_rate', 89.0))
                
                result = calculate_creator_payout(c_id, payout_rate, start_iso, end_iso)
                
                if result['creator_share'] > 0:
                    try:
                        payout_id = str(uuid.uuid4())
                        supabase.table('payouts').insert({
                            "id": payout_id,
                            "creator_id": c_id,
                            "cycle_start_date": bulk_start.isoformat(),
                            "cycle_end_date": bulk_end.isoformat(),
                            "gross_amount_inr": result['total_gross'],
                            "razorpay_fees_inr": result['total_fees'],
                            "tax_inr": result['total_tax'],
                            "refunds_deducted_inr": result['total_refunds'],
                            "platform_commission_inr": result['platform_commission'],
                            "creator_share_inr": result['creator_share'],
                            "status": "PENDING",
                            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                        }).execute()
                        
                        ids_to_lock = [p['id'] for p in result['unsettled_payments'] if 'id' in p]
                        for i in range(0, len(ids_to_lock), 100):
                            supabase.table('payments').update({"is_settled": True, "payout_id": payout_id}).in_('id', ids_to_lock[i:i+100]).execute()
                            
                        total_processed += 1
                        total_amount += result['creator_share']
                    except Exception as e:
                        st.error(f"Failed for {creator.get('creator_handle', c_id)}: {e}")
                
                progress_bar.progress((idx + 1) / len(creator_list))
            
            status_text.empty()
            progress_bar.empty()
            st.success(f"🎉 **Bulk Payout Complete!** Generated **{total_processed}** payouts totaling **{format_inr(total_amount)}**.")
            st.balloons()
            st.rerun()

# ==============================================================================
# TAB 3: PAYOUT HISTORY & RECONCILIATION
# ==============================================================================
with tab_history:
    st.markdown("### 📜 Payout Ledger")
    st.caption("Track the status of all generated payouts.")
    
    if st.button("🔄 Refresh History Data"):
        st.rerun()

    with st.spinner("Loading payout history..."):
        payouts_data = fetch_all(lambda: supabase.table('payouts').select(
            '*, creators:creator_id(creator_handle, creator_code)'
        ).order('created_at', desc=True))
        
    if not payouts_data:
        st.info("No payouts generated yet.")
    else:
        df_payouts = pd.DataFrame(payouts_data)
        
        # Safe column defaults
        if 'status' not in df_payouts.columns: df_payouts['status'] = 'UNKNOWN'
        if 'transaction_ref' not in df_payouts.columns: df_payouts['transaction_ref'] = 'N/A'
        if 'creator_share_inr' not in df_payouts.columns: df_payouts['creator_share_inr'] = 0
        if 'created_at' not in df_payouts.columns: df_payouts['created_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        def get_creator_name(x):
            if isinstance(x, dict) and x:
                return f"{x.get('creator_handle', 'Unknown')} ({x.get('creator_code', '?')})"
            return 'Unknown'

        df_payouts['Creator'] = df_payouts.get('creators', pd.Series([None] * len(df_payouts))).apply(get_creator_name)
        df_payouts['Payout Amount'] = df_payouts['creator_share_inr'].apply(format_inr)
        
        def get_cycle_str(row):
            start = row.get('cycle_start_date')
            end = row.get('cycle_end_date')
            if start and end:
                try:
                    return f"{pd.to_datetime(start).strftime('%d %b')} - {pd.to_datetime(end).strftime('%d %b')}"
                except Exception:
                    return "N/A"
            return "N/A"

        df_payouts['Cycle'] = df_payouts.apply(get_cycle_str, axis=1)
        df_payouts['Generated On'] = pd.to_datetime(df_payouts['created_at']).dt.strftime('%d %b %Y %H:%M')
        df_payouts['UTR / Ref'] = df_payouts['transaction_ref'].apply(lambda x: x if x and str(x) != 'nan' else 'N/A')

        display_cols = ['Generated On', 'Creator', 'Cycle', 'Payout Amount', 'status', 'UTR / Ref']
        
        st.dataframe(df_payouts[display_cols], width="stretch", hide_index=True, column_config={
            "status": st.column_config.SelectboxColumn("Status", options=["PENDING", "PAID", "FAILED", "UNKNOWN"]),
            "UTR / Ref": st.column_config.TextColumn("UTR / Ref Number")
        })
        
        st.divider()
        
        # --- MARK AS PAID ---
        st.markdown("### ✍️ Update Payout Status (Mark as Paid)")
        pending_payouts = [p for p in payouts_data if p.get('status') == 'PENDING']
        if not pending_payouts:
            st.success("🎉 No pending payouts. All creators have been paid!")
        else:
            pending_options = {f"{get_creator_name(p.get('creators'))} - {format_inr(p.get('creator_share_inr', 0))} ({pd.to_datetime(p['created_at']).strftime('%d %b')})": p['id'] for p in pending_payouts}
            
            with st.form("update_status_form"):
                c1, c2 = st.columns(2)
                with c1:
                    sel_payout_label = st.selectbox("Select Payout", options=list(pending_options.keys()), key="mark_paid_sel")
                    sel_payout_id = pending_options[sel_payout_label]
                with c2:
                    utr_number = st.text_input("Enter UTR / Transaction Ref", placeholder="e.g., UPI-616330527727")
                    
                if st.form_submit_button("✅ Mark as PAID", type="primary", width="stretch"):
                    if not utr_number.strip():
                        st.error("Please enter the transaction reference.")
                    else:
                        try:
                            supabase.table('payouts').update({
                                "status": "PAID",
                                "transaction_ref": utr_number.strip(),
                                "payout_date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                            }).eq('id', sel_payout_id).execute()
                            st.success("✅ Payout marked as PAID!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to update: {e}")

        st.divider()

        # --- DOWNLOAD PDF ---
        st.markdown("### 📄 Download Official Payout Receipts (PDF)")
        paid_payouts = [p for p in payouts_data if p.get('status') == 'PAID']
        if paid_payouts:
            paid_options = {f"{get_creator_name(p.get('creators'))} - {format_inr(p.get('creator_share_inr', 0))} ({pd.to_datetime(p['created_at']).strftime('%d %b')})": p for p in paid_payouts}
            
            sel_pdf_label = st.selectbox("Select Paid Payout", options=list(paid_options.keys()), key="pdf_sel")
            sel_pdf_payout = paid_options[sel_pdf_label]
            
            c_id = sel_pdf_payout['creator_id']
            c_data = (supabase.table('creators').select('*').eq('id', c_id).execute().data or [{}])[0]
            f_data = (supabase.table('creator_financial_info').select('*').eq('creator_id', c_id).execute().data or [{}])[0]
            
            pdf_bytes = generate_payout_pdf(sel_pdf_payout, c_data, f_data)
            st.download_button(
                label="⬇️ Download PDF Receipt",
                data=pdf_bytes,
                file_name=f"StreamHeart_Payout_{c_data.get('creator_handle', 'Creator')}_{pd.to_datetime(sel_pdf_payout['created_at']).strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                width="stretch"
            )
        else:
            st.info("No paid payouts available to generate receipts for.")

        st.divider()

        # --- ROLLBACK ---
        st.markdown("### ️ Rollback / Delete Payout (Emergency Use)")
        st.caption("Use this ONLY if you generated a payout by mistake and haven't sent the money yet.")
        
        rollback_options = {f"{get_creator_name(p.get('creators'))} - {format_inr(p.get('creator_share_inr', 0))} ({pd.to_datetime(p['created_at']).strftime('%d %b %Y')})": p['id'] for p in payouts_data}
        
        with st.form("rollback_form"):
            sel_rollback_label = st.selectbox("Select Payout to Rollback", options=list(rollback_options.keys()), key="rollback_sel")
            sel_rollback_id = rollback_options[sel_rollback_label]
            
            if st.form_submit_button("⚠️ Rollback & Unlock Payments", type="secondary", width="stretch"):
                try:
                    supabase.table('payments').update({"is_settled": False, "payout_id": None}).eq('payout_id', sel_rollback_id).execute()
                    supabase.table('payouts').delete().eq('id', sel_rollback_id).execute()
                    st.success("✅ Payout rolled back successfully.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Rollback failed: {e}")
