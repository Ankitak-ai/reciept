# pages/9_Receipts.py
import streamlit as st
import pandas as pd
import traceback
from utils.supabase_client import supabase
from utils.auth import require_auth
from utils.pdf_receipt_generator import generate_receipt_pdf, upload_receipt_to_supabase, format_inr

require_auth()

st.set_page_config(page_title="Payout Receipts", page_icon="📄", layout="wide")
st.title("📄 Payout Receipt Generation")

# Fetch Company Details
try:
    company_res = supabase.table('company_settings').select('setting_key', 'setting_value').execute()
    company = {row['setting_key']: row['setting_value'] for row in company_res.data}
except Exception as e:
    st.error(f"❌ Failed to load company settings: {e}")
    company = {}

tab_generate, tab_ledger = st.tabs(["🚀 Generate Receipts", "📜 Receipt Ledger"])

# ==============================================================================
# TAB 1: GENERATE RECEIPTS
# ==============================================================================
with tab_generate:
    st.markdown("### 📄 Generate Receipts for Paid Payouts")
    st.info("💡 Receipts can only be generated for payouts marked as **PAID**.")
    
    try:
        payouts_res = supabase.table('payouts').select(
            '*, creators:creator_id(id, creator_handle, creator_code, email, phone_number, financial_info:creator_financial_info(*))'
        ).eq('status', 'PAID').order('created_at', desc=True).execute()
        
        paid_payouts = payouts_res.data or []
        
        if not paid_payouts:
            st.warning("No paid payouts found. Go to Payouts page and mark a payout as PAID first.")
        else:
            existing_receipts_res = supabase.table('payout_receipts').select('payout_id').execute()
            existing_payout_ids = [r['payout_id'] for r in existing_receipts_res.data] if existing_receipts_res.data else []
            
            pending_payouts = [p for p in paid_payouts if p['id'] not in existing_payout_ids]
            
            if not pending_payouts:
                st.success("✅ All paid payouts already have receipts generated!")
            else:
                st.markdown(f"**{len(pending_payouts)}** payouts need receipts.")
                
                if st.button("📄 Generate All Pending Receipts", type="primary", use_container_width=True):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    success_count = 0
                    
                    for idx, payout in enumerate(pending_payouts):
                        creator = payout['creators']
                        creator_name = creator['creator_handle'] if creator else 'Unknown'
                        status_text.text(f"Generating 2-page receipt for {creator_name}...")
                        
                        try:
                            # 1. Generate sequential receipt number
                            today = __import__('datetime').datetime.now()
                            prefix = f"SH-PAYOUT-{today.strftime('%Y%m')}"
                            res = supabase.table('payout_receipts').select('receipt_number').like('receipt_number', f'{prefix}-%').order('receipt_number', desc=True).limit(1).execute()
                            new_num = int(res.data[0]['receipt_number'].split('-')[-1]) + 1 if res.data else 1
                            receipt_number = f"{prefix}-{str(new_num).zfill(6)}"
                            
                            # 2. Build the 2-Page PDF (Returns bytes and the true SHA256 hash of the final PDF)
                            pdf_bytes, final_pdf_hash = generate_receipt_pdf(payout, creator, company, receipt_number)
                            
                            # 3. Upload to Private Storage Bucket
                            pdf_url = upload_receipt_to_supabase(supabase, pdf_bytes, receipt_number)
                            
                            # 4. Save to Database
                            supabase.table('payout_receipts').insert({
                                "receipt_number": receipt_number,
                                "payout_id": payout['id'],
                                "creator_id": creator['id'],
                                "gross_amount": payout['gross_amount_inr'],
                                "net_amount": payout['creator_share_inr'],
                                "pdf_url": pdf_url,
                                "receipt_hash": final_pdf_hash,
                                "generated_by": st.session_state.get('user_email', 'System')
                            }).execute()
                            
                            success_count += 1
                        except Exception as e:
                            st.error(f"Failed for {creator_name}: {str(e)}")
                        
                        progress_bar.progress((idx + 1) / len(pending_payouts))
                    
                    status_text.text("")
                    progress_bar.empty()
                    
                    if success_count > 0:
                        st.success(f"✅ Successfully generated and uploaded {success_count} receipts!")
                        st.rerun()
                        
    except Exception as e:
        st.error(f"❌ Failed to fetch payouts: {e}")
        st.code(traceback.format_exc())

# ==============================================================================
# TAB 2: RECEIPT LEDGER
# ==============================================================================
with tab_ledger:
    st.markdown("### 📜 Generated Receipts Ledger")
    
    try:
        receipts_res = supabase.table('payout_receipts').select(
            '*, creators:creator_id(creator_handle, creator_code)'
        ).order('generated_at', desc=True).execute()
        
        if not receipts_res.data:
            st.info("No receipts have been generated yet.")
        else:
            df_receipts = pd.DataFrame(receipts_res.data)
            df_receipts['Creator'] = df_receipts['creators'].apply(lambda x: x['creator_handle'] if x else 'Unknown')
            df_receipts['Gross'] = df_receipts['gross_amount'].apply(lambda x: f"₹{x/100:.2f}" if x else "₹0.00")
            df_receipts['Net Payout'] = df_receipts['net_amount'].apply(lambda x: f"₹{x/100:.2f}" if x else "₹0.00")
            
            st.dataframe(df_receipts[['generated_at', 'receipt_number', 'Creator', 'Gross', 'Net Payout']], 
                        use_container_width=True, hide_index=True)
            
            st.divider()
            st.markdown("### ⬇️ Download Receipts")
            
            for _, row in df_receipts.iterrows():
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.write(f"**{row['receipt_number']}** - {row['Creator']} ({row['Net Payout']})")
                with col2:
                    st.caption("Generated: " + str(row['generated_at'])[:10])
                with col3:
                    if st.button("⬇️ Download PDF", key=row['id']):
                        st.components.v1.html(f'<script>window.open("{row["pdf_url"]}", "_blank");</script>', height=0)
    except Exception as e:
        st.error(f"❌ Failed to load receipts: {e}")
