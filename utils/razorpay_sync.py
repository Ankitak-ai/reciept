import requests
import streamlit as st
import time
from utils.supabase_client import supabase

def sync_razorpay_payments():
    """
    Fetches payments from Razorpay, matches them to creators via receipt prefix,
    and stores them in the Supabase database with raw JSONB payloads.
    """
    # 1. Fetch credentials strictly from Streamlit Secrets
    try:
        key_id = st.secrets["RAZORPAY_KEY_ID"]
        key_secret = st.secrets["RAZORPAY_KEY_SECRET"]
    except KeyError:
        st.error("⚠️ Missing RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET in Streamlit Secrets.")
        return None, None, None
    
    # 2. Initialize metrics tracking
    metrics = {"fetched": 0, "inserted": 0, "duplicate": 0, "unmapped": 0, "errors": 0}
    unmapped_receipts = []
    error_logs = []

    # 3. Fetch all creators into a map for O(1) lookup by creator_code
    creators_res = supabase.table('creators').select('id, creator_code').execute()
    creators_map = {c['creator_code']: c['id'] for c in creators_res.data}

    try:
        # 4. Fetch payments from Razorpay API (fetching last 100 for this sync batch)
        response = requests.get(
            "https://api.razorpay.com/v1/payments?count=100",
            auth=(key_id, key_secret),
            timeout=15
        )
        response.raise_for_status()
        payments_data = response.json().get("items", [])
        metrics["fetched"] = len(payments_data)

        for payment in payments_data:
            payment_id = payment.get("id")
            order_id = payment.get("order_id")
            
            # 5. Duplicate Check
            existing = supabase.table('payments').select('id').eq('payment_id', payment_id).execute()
            if existing.data:
                metrics["duplicate"] += 1
                continue

            raw_order_payload = None
            creator_id = None

            # 6. Fetch order details if order_id exists
            if order_id:
                try:
                    # Rate limit handling: small delay to respect Razorpay limits (100ms)
                    time.sleep(0.1) 
                    
                    order_response = requests.get(
                        f"https://api.razorpay.com/v1/orders/{order_id}",
                        auth=(key_id, key_secret),
                        timeout=15
                    )
                    
                    if order_response.status_code == 200:
                        order_data = order_response.json()
                        raw_order_payload = order_data
                        receipt = order_data.get("receipt", "")
                        
                        # 7. Parse creator_code from receipt (e.g., "mc_rp_carryminati" -> matches "mc")
                        if receipt:
                            for code, cid in creators_map.items():
                                if receipt.startswith(f"{code}_"):
                                    creator_id = cid
                                    break
                            
                            if not creator_id:
                                metrics["unmapped"] += 1
                                unmapped_receipts.append({"payment_id": payment_id, "receipt": receipt})
                    else:
                        metrics["errors"] += 1
                        error_logs.append(f"Invalid order ID {order_id}: {order_response.status_code} - {order_response.text}")
                        
                except requests.exceptions.RequestException as e:
                    metrics["errors"] += 1
                    error_logs.append(f"Order fetch failed for {order_id}: {str(e)}")

            # 8. Insert payment into database
            try:
                payment_record = {
                    "payment_id": payment_id,
                    "order_id": order_id,
                    "creator_id": creator_id,
                    "amount": payment.get("amount"),
                    "fee": payment.get("fee"),
                    "tax": payment.get("tax"),
                    "status": payment.get("status"),
                    "method": payment.get("method"),
                    "email": payment.get("email"),
                    "contact": payment.get("contact"),
                    "created_at": payment.get("created_at"),
                    "raw_payment_payload": payment,
                    "raw_order_payload": raw_order_payload
                }
                
                supabase.table('payments').insert(payment_record).execute()
                metrics["inserted"] += 1
                
            except Exception as e:
                metrics["errors"] += 1
                error_logs.append(f"DB Insert failed for {payment_id}: {str(e)}")

        return metrics, unmapped_receipts, error_logs

    except requests.exceptions.RequestException as e:
        st.error(f"❌ Failed to connect to Razorpay API: {str(e)}")
        return None, None, None
