import streamlit as st
import pandas as pd
import datetime
import uuid
import io
from zoneinfo import ZoneInfo
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

tab_generate, tab_history = st.tabs(["🚀 Generate New Payout", "📜 Payout History & Reconciliation"])

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
    p.drawString(50, height - 140, f"Payout ID: {payout['id'][:8]}...")
    p.drawString(50, height - 160, f"Generated: {pd.to_datetime(payout['created_at']).strftime('%d %b %Y')}")
    
    p.setFont("Helvetica", 12)
    y = height - 200
    p.drawString(50, y, f"Cycle: {pd.to_datetime(payout['cycle_start']).strftime('%d %b')} to {pd.to_datetime(payout['cycle_end']).strftime('%d %b')}")
    y -= 25
    p.drawString(50, y, f"Gross Volume: {format_inr(payout['total_gmv_inr'])}")
    y -= 20
    p.drawString(50, y, f"Refunds Deducted: {format_inr(payout['total_refunds_inr'])}")
    y -= 20
    p.drawString(50, y, f"Adjusted Gross: {format_inr(payout['adjusted_gross_inr'])}")
    y -= 20
    p.drawString(50, y, f"Platform Commission: {format_inr(payout['platform_fee_inr'])}")
    
    p.setFont("Helvetica-Bold", 16)
    y -= 40
    p.drawString(50, y, f"NET PAYOUT TRANSFERRED: {format_inr(payout['creator_share_inr'])}")
    
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
        
    if payout.get('utr'):
        y -= 40
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y, f"UTR / Bank Ref: {payout['utr']}")
        y -= 20
        paid_date = pd.to_datetime(payout['paid_at']).strftime('%d %b %Y %H:%M') if payout.get('paid_at') else 'N/A'
        p.drawString(50, y, f"Paid On: {paid_date}")
        
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer.read()

# ==============================================================================
# TAB 1: GENERATE NEW PAYOUT
# ==============================================================================
with tab_generate:
    st.markdown("### 📅 Select Payout Cycle (All dates calculated in IST)")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        cycle_start = st.date_input("Cycle Start Date", value=today_ist.replace(day=1))
    with col2:
        cycle_end = st.date_input("Cycle End Date", value=today_ist)
    with col3:
        creators_res = supabase.table('creators').select('id, creator_handle, creator_code, payout_rate').eq('status', 'ACTIVE').order('creator_handle').execute()
        creators_list = creators_res.data or []
        creator_options = {f"{c['creator_handle']} ({c['creator_code']})": c for c in creators_list}
        
        if not creator_options:
            st.warning("No active creators found.")
            selected_creator = None
        else:
            selected_label = st.selectbox("Select Creator", options=list(creator_options.keys()))
            selected_creator = creator_options[selected_label]

    if selected_creator:
        creator_id = selected_creator['id']
        payout_rate = float(selected_creator.get('payout_rate', 89.0))
        
        # Fetch Bank Details for Verification
        fin_res = supabase.table('creator_financial_info').select('*').eq('creator_id', creator_id).execute()
        fin_info = fin_res.data[0] if fin_res.data else {}
        
        st.info(f"🏦 **Verify Bank Details Before Generating:**\n\n"
                f"**Name:** {fin_info.get('legal_name') or 'N/A'} | "
                f"**UPI:** {fin_info.get('upi_id') or 'N/A'} | "
                f"**Bank:** {fin_info.get('bank_name') or 'N/A'} (A/C: XXXX{fin_info.get('account_number_last4') or 'N/A'})")
        
        start_dt_ist = datetime.datetime.combine(cycle_start, datetime.time.min, tzinfo=IST)
        end_dt_ist = datetime.datetime.combine(cycle_end, datetime.time.max, tzinfo=IST)
        start_iso = start_dt_ist.astimezone(datetime.timezone.utc).isoformat()
        end_iso = end_dt_ist.astimezone(datetime.timezone.utc).isoformat()
        
        st.caption(f"🕒 Querying from: **{cycle_start.strftime('%d/%m/%Y %H:%M')} IST** to **{cycle_end.strftime('%d/%m/%Y %H:%M')} IST**")
        
        with st.spinner("Calculating unsettled earnings..."):
            # ✅ FIX 1: Using fetch_all to ensure we don't miss a single unsettled tip
            unsettled_payments = fetch_all(lambda: supabase.table('payments').select(
                'id, amount_inr, fee_inr, tax_inr'
            ).eq('creator_id', creator_id).eq('is_settled', False).gte('created_at', start_iso).lte('created_at', end_iso))
            
            # ✅ FIX 2: Bulletproof Refund Fetching (Avoids PostgREST Join Errors)
            # Step A: Fetch all refunds in this cycle
            cycle_refunds = fetch_all(lambda: supabase.table('refunds').select(
                'amount_inr, payment_id'
            ).gte('created_at', start_iso).lte('created_at', end_iso))
            
            # Step B: Get all payment IDs that belong to this creator
            creator_payments_res = fetch_all(lambda: supabase.table('payments').select(
                'payment_id'
            ).eq('creator_id', creator_id))
            creator_payment_ids = set(p['payment_id'] for p in creator_payments_res)
            
            # Step C: Filter refunds specifically for this creator in Python
            creator_refunds = [
                r for r in cycle_refunds 
                if r.get('payment_id') in creator_payment_ids
            ]

        total_gross = sum(p.get('amount_inr', 0) or 0 for p in unsettled_payments)
        total_gateway_fees = sum((p.get('fee_inr', 0) or 0) + (p.get('tax_inr', 0) or 0) for p in unsettled_payments)
        total_refunds = sum(r.get('amount_inr', 0) or 0 for r in creator_refunds)
        
        adjusted_gross = total_gross - total_refunds
        creator_share = round(adjusted_gross * (payout_rate / 100))
        platform_commission = adjusted_gross - creator_share
        
        st.divider()
        
        if total_gross == 0:
            st.info("📭 No unsettled payments found for the selected IST date range.")
        else:
            st.markdown("### 🧮 Payout Preview")
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Gross Donations", format_inr(total_gross))
            m2.metric("Less: Refunds", format_inr(total_refunds), delta_color="inverse" if total_refunds > 0 else "off")
            m3.metric("Adjusted Gross", format_inr(adjusted_gross))
            m4.metric(f"Creator Share ({payout_rate}%)", format_inr(creator_share))
            m5.metric("Platform Fee", format_inr(platform_commission))
            
            st.divider()
            
            with st.form("generate_payout_form"):
                st.markdown("### 📝 Finalize & Lock Payout")
                notes = st.text_area("Admin Notes (Optional)", placeholder="e.g., Standard monthly payout, or adjusting for X...")
                
                submitted = st.form_submit_button("🔒 Generate & Lock Payout Record", type="primary", width="stretch")
                
                if submitted:
                    try:
                        payout_id = str(uuid.uuid4())
                        
                        # 1. Insert into Payouts Ledger
                        supabase.table('payouts').insert({
                            "id": payout_id,
                            "creator_id": creator_id,
                            "cycle_start": start_iso,
                            "cycle_end": end_iso,
                            "total_gmv_inr": total_gross,
                            "total_refunds_inr": total_refunds,
                            "adjusted_gross_inr": adjusted_gross,
                            "creator_share_inr": creator_share,
                            "platform_fee_inr": platform_commission,
                            "gateway_fee_inr": total_gateway_fees,
                            "status": "PENDING",
                            "notes": notes
                        }).execute()
                        
                        # 2. Lock the underlying payments (Mark as settled in chunks of 100)
                        ids_to_lock = [p['id'] for p in unsettled_payments if 'id' in p]
                        
                        for i in range(0, len(ids_to_lock), 100):
                            chunk = ids_to_lock[i:i+100]
                            supabase.table('payments').update({
                                "is_settled": True, 
                                "payout_id": payout_id
                            }).in_('id', chunk).execute()
                            
                        st.success(f"✅ Payout of {format_inr(creator_share)} generated and locked successfully!")
                        st.balloons()
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Failed to generate payout: {e}")

# ==============================================================================
# TAB 2: PAYOUT HISTORY & RECONCILIATION
# ==============================================================================
with tab_history:
    st.markdown("### 📜 Payout Ledger")
    st.caption("Track the status of all generated payouts. Mark them as PAID once the bank transfer is complete.")
    
    with st.spinner("Loading payout history..."):
        # ✅ FIX: Using fetch_all so the history table never truncates at 1000 rows
        payouts_data = fetch_all(lambda: supabase.table('payouts').select(
            '*, creators:creator_id(creator_handle, creator_code)'
        ).order('created_at', desc=True))
        
    if not payouts_data:
        st.info("No payouts generated yet.")
    else:
        df_payouts = pd.DataFrame(payouts_data)
        df_payouts['Creator'] = df_payouts['creators'].apply(lambda x: f"{x['creator_handle']} ({x['creator_code']})" if x else 'Unknown')
        df_payouts['Payout Amount'] = df_payouts['creator_share_inr'].apply(format_inr)
        df_payouts['Cycle'] = df_payouts.apply(lambda row: f"{pd.to_datetime(row['cycle_start']).strftime('%d %b')} - {pd.to_datetime(row['cycle_end']).strftime('%d %b')}", axis=1)
        df_payouts['Generated On'] = pd.to_datetime(df_payouts['created_at']).dt.strftime('%d %b %Y %H:%M')
        
        display_cols = ['Generated On', 'Creator', 'Cycle', 'Payout Amount', 'status', 'utr']
        st.dataframe(df_payouts[display_cols], width="stretch", hide_index=True, column_config={
            "status": st.column_config.SelectboxColumn("Status", options=["PENDING", "PAID", "FAILED"]),
            "utr": st.column_config.TextColumn("UTR / Ref Number")
        })
        
        st.divider()
        st.markdown("### ✍️ Update Payout Status (Mark as Paid)")
        
        pending_payouts = [p for p in payouts_data if p['status'] == 'PENDING']
        if not pending_payouts:
            st.success("🎉 No pending payouts. All creators have been paid!")
        else:
            pending_options = {f"{p['creators']['creator_handle']} - {format_inr(p['creator_share_inr'])} ({pd.to_datetime(p['created_at']).strftime('%d %b')})": p['id'] for p in pending_payouts}
            
            with st.form("update_status_form"):
                c1, c2 = st.columns(2)
                with c1:
                    sel_payout_label = st.selectbox("Select Payout", options=list(pending_options.keys()))
                    sel_payout_id = pending_options[sel_payout_label]
                with c2:
                    utr_number = st.text_input("Enter UTR / Bank Ref Number", placeholder="e.g., UTIB1234567890")
                    
                update_submitted = st.form_submit_button("✅ Mark as PAID", type="primary", width="stretch")
                
                if update_submitted:
                    if not utr_number.strip():
                        st.error("Please enter the UTR number for audit trails.")
                    else:
                        try:
                            supabase.table('payouts').update({
                                "status": "PAID",
                                "utr": utr_number.strip().upper(),
                                "paid_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                            }).eq('id', sel_payout_id).execute()
                            st.success("✅ Payout marked as PAID!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to update: {e}")

        st.divider()
        st.markdown("### 📄 Download Official Payout Receipts (PDF)")
        st.caption("Generate official PDF receipts for your records or to send to creators.")
        
        paid_payouts = [p for p in payouts_data if p['status'] == 'PAID']
        if paid_payouts:
            paid_options = {f"{p['creators']['creator_handle']} - {format_inr(p['creator_share_inr'])} ({pd.to_datetime(p['created_at']).strftime('%d %b')})": p for p in paid_payouts}
            
            sel_pdf_label = st.selectbox("Select Paid Payout", options=list(paid_options.keys()), key="pdf_sel")
            sel_pdf_payout = paid_options[sel_pdf_label]
            
            # Fetch full creator and financial info for the PDF
            c_id = sel_pdf_payout['creator_id']
            c_res = supabase.table('creators').select('*').eq('id', c_id).execute()
            c_data = c_res.data[0] if c_res.data else {}
            f_res = supabase.table('creator_financial_info').select('*').eq('creator_id', c_id).execute()
            f_data = f_res.data[0] if f_res.data else {}
            
            pdf_bytes = generate_payout_pdf(sel_pdf_payout, c_data, f_data)
            st.download_button(
                label="⬇️ Download PDF Receipt",
                data=pdf_bytes,
                file_name=f"StreamHeart_Payout_{sel_pdf_payout['creators']['creator_handle']}_{pd.to_datetime(sel_pdf_payout['created_at']).strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                width="stretch"
            )

    st.divider()
    st.markdown("### 🗑️ Rollback / Delete Payout (Emergency Use)")
    st.caption("Use this ONLY if you generated a payout by mistake and haven't sent the money yet. This unlocks the payments so they can be recalculated.")
    
    if payouts_data:
        rollback_options = {f"{p['creators']['creator_handle']} - {format_inr(p['creator_share_inr'])} ({pd.to_datetime(p['created_at']).strftime('%d %b %Y')})": p['id'] for p in payouts_data}
        
        with st.form("rollback_form"):
            sel_rollback_label = st.selectbox("Select Payout to Rollback", options=list(rollback_options.keys()), key="rollback_sel")
            sel_rollback_id = rollback_options[sel_rollback_label]
            
            confirm_rollback = st.form_submit_button("⚠️ Rollback & Unlock Payments", type="secondary", width="stretch")
            
            if confirm_rollback:
                try:
                    # 1. Unlock payments
                    supabase.table('payments').update({"is_settled": False, "payout_id": None}).eq('payout_id', sel_rollback_id).execute()
                    # 2. Delete payout record
                    supabase.table('payouts').delete().eq('id', sel_rollback_id).execute()
                    
                    st.success("✅ Payout rolled back successfully. Payments are now unsettled and ready for recalculation.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Rollback failed: {e}")
