import streamlit as st
import pandas as pd
import requests
import io
import time
from utils.auth import require_auth
from utils.supabase_client import supabase

require_auth()
st.set_page_config(page_title="Emergency Payouts", page_icon="🚨", layout="wide")
st.title("🚨 Emergency Payout Generator (Direct from Razorpay)")
st.warning("**Bypasses Supabase DB.** Pulls raw data directly from Razorpay to ensure 100% accuracy for today's payouts.")

# 1. Get Credentials
key_id = st.secrets.get("RAZORPAY_KEY_ID")
key_secret = st.secrets.get("RAZORPAY_KEY_SECRET")

if not key_id or not key_secret:
    st.error("Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to Streamlit Secrets!")
    st.stop()

auth_header = "Basic " + requests.compat.base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()

# 2. Fetch Creators from Supabase
creators_res = supabase.table("creators").select("id, creator_code, creator_handle, payout_rate").execute()
creators_map = {c['creator_code']: {'handle': c['creator_handle'], 'rate': float(c.get('payout_rate', 89))} for c in creators_res.data}

if st.button("🔄 Fetch Raw Data from Razorpay & Generate Payouts", type="primary"):
    all_payments = []
    skip = 0
    count = 100
    
    with st.spinner("Fetching all captured payments from Razorpay..."):
        while True:
            url = f"https://api.razorpay.com/v1/payments?count={count}&skip={skip}&status=captured"
            res = requests.get(url, headers={"Authorization": auth_header})
            if not res.ok:
                st.error(f"Razorpay API Error: {res.text}")
                break
            data = res.json().get("items", [])
            if not data: break
            all_payments.extend(data)
            if len(data) < count: break
            skip += count
            time.sleep(0.2) # Rate limit safety

    st.info(f"Fetched {len(all_payments)} payments. Now fetching order details to map creators...")
    
    creator_totals = {}
    progress = st.progress(0)
    
    for i, p in enumerate(all_payments):
        progress.progress((i + 1) / len(all_payments))
        receipt = ""
        
        # Fetch order to get receipt
        if p.get("order_id"):
            time.sleep(0.05) # Rate limit
            o_res = requests.get(f"https://api.razorpay.com/v1/orders/{p['order_id']}", headers={"Authorization": auth_header})
            if o_res.ok:
                receipt = o_res.json().get("receipt", "")
                
        # Map to creator
        creator_code = None
        if receipt:
            for code in creators_map.keys():
                if receipt == code or receipt.startswith(f"{code}_"):
                    creator_code = code
                    break
                    
        if creator_code:
            amount_inr = p.get("amount", 0) / 100.0
            if creator_code not in creator_totals:
                creator_totals[creator_code] = {'gross': 0.0, 'count': 0}
            creator_totals[creator_code]['gross'] += amount_inr
            creator_totals[creator_code]['count'] += 1

    # 3. Build Payout DataFrame
    payout_data = []
    for code, data in creator_totals.items():
        info = creators_map[code]
        gross = data['gross']
        rate = info['rate']
        net_payout = round(gross * (rate / 100), 2)
        
        payout_data.append({
            "Creator Code": code,
            "Creator Handle": info['handle'],
            "Total Gross (₹)": round(gross, 2),
            "Payout Rate (%)": rate,
            "Net Payout Amount (₹)": net_payout,
            "Total Payments": data['count']
        })
        
    df_payouts = pd.DataFrame(payout_data)
    df_payouts = df_payouts.sort_values(by="Net Payout Amount (₹)", ascending=False)
    
    st.success(f"✅ Generated payouts for {len(df_payouts)} creators!")
    st.dataframe(df_payouts, use_container_width=True)
    
    # 4. Download CSV
    csv = df_payouts.to_csv(index=False)
    st.download_button(
        label="📥 Download Payout CSV for Bank Transfer",
        data=csv,
        file_name="emergency_creator_payouts.csv",
        mime="text/csv",
        type="primary"
    )
