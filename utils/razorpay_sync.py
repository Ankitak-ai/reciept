import requests
import streamlit as st
import time
import datetime
from utils.supabase_client import supabase

def sync_razorpay_payments():
    try:
        key_id = st.secrets["RAZORPAY_KEY_ID"]
        key_secret = st.secrets["RAZORPAY_KEY_SECRET"]
    except KeyError:
        st.error("⚠️ Missing RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET in Streamlit Secrets.")
        return None, None, None
    
    metrics = {"fetched": 0, "inserted": 0, "duplicate": 0, "unmapped": 0, "errors": 0}
    unmapped_receipts = []
    error_logs = []

    creators_res = supabase.table('creators').select('id, creator_code').execute()
    creators_map = {c['creator_code']: c['id'] for c in creators_res.data}

    try:
        # ==========================================
        # 1. ROBUST PAGINATION LOGIC (Fetch ALL successful payments)
        # ==========================================
        skip = 0
        count = 100
        to_timestamp = None
        all_payments = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text("Fetching successful payments from Razorpay...")

        while True:
            # FIX: Added &status=captured to ONLY fetch successful, collected payments.
            # This filters out 'failed' and 'authorized' (pending) payments at the API level.
            url = f"https://api.razorpay.com/v1/payments?count={count}&status=captured"
            
            # Use time-based pagination after 1000 records to avoid Razorpay's skip limit
            if to_timestamp:
                url += f"&to={to_timestamp}"
            else:
                url += f"&skip={skip}"
                
            response = requests.get(url, auth=(key_id, key_secret), timeout=15)
            response.raise_for_status()
            payments_data = response.json().get("items", [])
            
            if not payments_data:
                break
                
            all_payments.extend(payments_data)
            metrics["fetched"] = len(all_payments)
            status_text.text(f"Fetched {metrics['fetched']} successful payments...")
            
            if len(payments_data) < count:
                break
                
            if to_timestamp:
                new_to = payments_data[-1]['created_at']
                # Infinite loop guard: If the oldest timestamp in this batch is identical 
                # to the previous batch, we've hit Razorpay's 1-second resolution limit.
                if new_to == to_timestamp:
                    st.warning(f"⚠️ Reached Razorpay's time-based pagination limit at timestamp {to_timestamp}. Over 100 successful payments occurred in the exact same second. Older payments beyond this point could not be fetched.")
                    break
                to_timestamp = new_to
            else:
                skip += count
                if skip >= 1000:
                    # Switch to time-based pagination to bypass Razorpay's 1000 skip limit
                    to_timestamp = payments_data[-1]['created_at']
                    skip = 0

            time.sleep(0.2) # Respect Razorpay rate limits

        progress_bar.empty()
        status_text.text(f"Processing {len(all_payments)} payments...")

        # ==========================================
        # 2. PROCESS AND INSERT PAYMENTS
        # ==========================================
        for idx, payment in enumerate(all_payments):
            payment_id = payment.get("id")
            order_id = payment.get("order_id")
            
            # Duplicate Check (Also handles overlapping time-based pagination batches)
            existing = supabase.table('payments').select('id').eq('payment_id', payment_id).execute()
            if existing.data:
                metrics["duplicate"] += 1
                continue

            raw_order_payload = None
            creator_id = None

            if order_id:
                try:
                    time.sleep(0.05) # Micro-delay for order fetches
                    
                    order_response = requests.get(
                        f"https://api.razorpay.com/v1/orders/{order_id}",
                        auth=(key_id, key_secret),
                        timeout=15
                    )
                    
                    if order_response.status_code == 200:
                        order_data = order_response.json()
                        raw_order_payload = order_data
                        receipt = order_data.get("receipt", "")
                        
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
                        error_logs.append(f"Invalid order ID {order_id}: {order_response.status_code}")
                        
                except requests.exceptions.RequestException as e:
                    metrics["errors"] += 1
                    error_logs.append(f"Order fetch failed for {order_id}: {str(e)}")

            try:
                # Convert Razorpay Unix timestamp to ISO 8601 string for PostgreSQL
                created_at_ts = payment.get("created_at")
                created_at_formatted = None
                if created_at_ts:
                    try:
                        dt_obj = datetime.datetime.fromtimestamp(created_at_ts, tz=datetime.timezone.utc)
                        created_at_formatted = dt_obj.isoformat()
                    except (ValueError, TypeError, OSError):
                        created_at_formatted = None

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
                    "created_at": created_at_formatted,
                    "raw_payment_payload": payment,
                    "raw_order_payload": raw_order_payload
                }
                
                supabase.table('payments').insert(payment_record).execute()
                metrics["inserted"] += 1
                
            except Exception as e:
                metrics["errors"] += 1
                error_logs.append(f"DB Insert failed for {payment_id}: {str(e)}")
                
            # Update progress bar during insertion
            if idx % 20 == 0:
                progress_bar.progress((idx + 1) / len(all_payments))

        progress_bar.empty()
        return metrics, unmapped_receipts, error_logs

    except requests.exceptions.RequestException as e:
        st.error(f"❌ Failed to connect to Razorpay API: {str(e)}")
        return None, None, None
