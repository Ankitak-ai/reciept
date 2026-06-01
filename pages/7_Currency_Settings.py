import streamlit as st
import pandas as pd
from utils.supabase_client import supabase

from utils.auth import require_auth
require_auth()

st.set_page_config(page_title="Currency Settings", page_icon="💱")
st.title("💱 Currency Conversion Settings")

st.info("💡 These rates are used to convert international Razorpay payments into your base currency (INR). Changes apply immediately to the next sync.")

# ==============================================================================
# 1. VIEW & EDIT RATES
# ==============================================================================
st.markdown("### 💱 Active Exchange Rates (to INR)")

rates_res = supabase.table('currency_rates').select('*').order('currency_code').execute()
df_rates = pd.DataFrame(rates_res.data)

if df_rates.empty:
    st.warning("No currency rates found.")
else:
    # Format the dataframe for display
    display_df = df_rates[['currency_code', 'rate_to_inr', 'updated_at']].copy()
    display_df.columns = ['Currency Code', 'Rate to INR', 'Last Updated']
    st.dataframe(display_df, use_container_width=True, hide_index=True)

st.markdown("---")
st.markdown("### ➕ Add or Update Currency Rate")

with st.form("update_rate_form"):
    col1, col2 = st.columns(2)
    with col1:
        currency_code = st.text_input("Currency Code (e.g., USD, EUR)", max_chars=3).upper()
    with col2:
        rate = st.number_input("Rate to INR (e.g., 83.50)", min_value=0.0001, format="%.4f")
    
    submitted = st.form_submit_button("Save Rate", use_container_width=True)
    
    if submitted:
        if not currency_code:
            st.error("Please enter a currency code.")
        else:
            try:
                # Upsert the rate
                supabase.table('currency_rates').upsert({
                    "currency_code": currency_code,
                    "rate_to_inr": rate
                }, on_conflict="currency_code").execute()
                st.success(f"✅ Rate for {currency_code} updated to {rate} successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to update rate: {e}")

# ==============================================================================
# 2. DELETE RATE
# ==============================================================================
st.markdown("---")
st.markdown("### 🗑️ Remove Currency Rate")
st.warning("Removing a rate will cause future payments in that currency to fallback to a 1.0 exchange rate.")

delete_col1, delete_col2 = st.columns([2, 1])
with delete_col1:
    currency_to_delete = st.selectbox(
        "Select currency to remove", 
        options=["None"] + df_rates['currency_code'].tolist()
    )
with delete_col2:
    st.write("") # Spacing
    st.write("") # Spacing
    if st.button("Delete Rate", type="secondary", use_container_width=True):
        if currency_to_delete == "None":
            st.warning("Please select a currency.")
        elif currency_to_delete == "INR":
            st.error("Cannot delete the base currency (INR).")
        else:
            supabase.table('currency_rates').delete().eq('currency_code', currency_to_delete).execute()
            st.success(f"✅ {currency_to_delete} rate removed.")
            st.rerun()
