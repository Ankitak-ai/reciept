import streamlit as st
import pandas as pd
import datetime
from utils.supabase_client import supabase
from utils.auth import require_auth

require_auth()

st.set_page_config(page_title="Currency Settings", page_icon="💱", layout="wide")
st.title("💱 Currency & Exchange Rate Settings")
st.caption("Manage supported currencies and their exchange rates relative to INR (Base Currency).")

# ==============================================================================
# 1. SAFE DATA FETCHING
# ==============================================================================
with st.spinner("Loading currency settings..."):
    # Fetch all currency rates
    res = supabase.table('currency_rates').select('*').order('currency_code').execute()
    data = res.data or []

# ==============================================================================
# 2. BULLETPROOF DATAFRAME & COLUMN HANDLING
# ==============================================================================
if data:
    df_rates = pd.DataFrame(data)
    
    # Safely identify the currency code column (handles 'currency_code', 'code', or 'currency')
    code_col = next((col for col in ['currency_code', 'code', 'currency'] if col in df_rates.columns), None)
    
    if code_col and code_col in df_rates.columns:
        # Drop NaNs and get unique values to prevent errors
        currency_options = ["None"] + df_rates[code_col].dropna().unique().tolist()
    else:
        # Fallback if the column name is completely unexpected
        currency_options = ["None", "USD", "INR", "EUR", "GBP", "CAD", "AUD"]
else:
    # Fallback if the table is completely empty
    currency_options = ["None", "USD", "INR", "EUR", "GBP", "CAD", "AUD"]
    df_rates = pd.DataFrame(columns=['currency_code', 'exchange_rate_to_inr', 'is_active', 'updated_at'])

# ==============================================================================
# 3. UI: VIEW CURRENT RATES
# ==============================================================================
st.markdown("### 📊 Current Exchange Rates")

if df_rates.empty:
    st.info("No currency rates configured yet. Add your first currency below!")
else:
    # Safely format the display dataframe
    display_df = df_rates.copy()
    
    # Ensure required columns exist for display
    if 'currency_code' not in display_df.columns:
        display_df['currency_code'] = display_df.get('code', 'UNKNOWN')
    if 'exchange_rate_to_inr' not in display_df.columns:
        display_df['exchange_rate_to_inr'] = 1.0
    if 'is_active' not in display_df.columns:
        display_df['is_active'] = True
        
    display_df['Rate (1 Foreign = X INR)'] = display_df['exchange_rate_to_inr'].apply(lambda x: f"₹{x:,.2f}" if pd.notnull(x) else "N/A")
    display_df['Status'] = display_df['is_active'].apply(lambda x: "✅ Active" if x else "❌ Inactive")
    
    st.dataframe(
        display_df[['currency_code', 'Rate (1 Foreign = X INR)', 'Status']], 
        width="stretch", 
        hide_index=True,
        column_config={
            "currency_code": st.column_config.TextColumn("Currency", width="small"),
            "Rate (1 Foreign = X INR)": st.column_config.TextColumn("Exchange Rate", width="medium"),
            "Status": st.column_config.TextColumn("Status", width="small")
        }
    )

st.divider()

# ==============================================================================
# 4. UI: ADD / EDIT CURRENCY
# ==============================================================================
st.markdown("### ⚙️ Manage Currencies")

tab_add, tab_edit = st.tabs(["➕ Add New Currency", "✏️ Edit Existing Currency"])

with tab_add:
    with st.form("add_currency_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            new_code = st.text_input("Currency Code (e.g., USD, EUR)", max_chars=3).strip().upper()
        with c2:
            new_rate = st.number_input("Exchange Rate (1 Foreign Unit = ? INR)", min_value=0.01, step=0.01, format="%.4f")
        with c3:
            new_active = st.checkbox("Active", value=True)
            
        submitted_add = st.form_submit_button("💾 Add Currency", type="primary", width="stretch")
        
        if submitted_add:
            if not new_code:
                st.error("Currency code is required (e.g., USD).")
            elif new_code in df_rates['currency_code'].values if 'currency_code' in df_rates.columns else False:
                st.error(f"Currency '{new_code}' already exists. Please edit it instead.")
            else:
                try:
                    supabase.table('currency_rates').insert({
                        "currency_code": new_code,
                        "exchange_rate_to_inr": new_rate,
                        "is_active": new_active,
                        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }).execute()
                    st.success(f"✅ Currency '{new_code}' added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to add currency: {e}")

with tab_edit:
    if df_rates.empty:
        st.warning("No currencies available to edit.")
    else:
        # Safely get the list of existing codes for the selectbox
        existing_codes = df_rates['currency_code'].dropna().unique().tolist() if 'currency_code' in df_rates.columns else []
        
        if not existing_codes:
            st.warning("No valid currency codes found to edit.")
        else:
            with st.form("edit_currency_form"):
                sel_code = st.selectbox("Select Currency to Edit", options=existing_codes)
                
                # Get current values safely
                current_row = df_rates[df_rates['currency_code'] == sel_code].iloc[0] if 'currency_code' in df_rates.columns else {}
                current_rate = float(current_row.get('exchange_rate_to_inr', 1.0))
                current_active = bool(current_row.get('is_active', True))
                
                c1, c2 = st.columns(2)
                with c1:
                    edit_rate = st.number_input("New Exchange Rate", min_value=0.01, step=0.01, value=current_rate, format="%.4f")
                with c2:
                    edit_active = st.checkbox("Active", value=current_active)
                    
                submitted_edit = st.form_submit_button("💾 Update Currency", type="primary", width="stretch")
                
                if submitted_edit:
                    try:
                        supabase.table('currency_rates').update({
                            "exchange_rate_to_inr": edit_rate,
                            "is_active": edit_active,
                            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                        }).eq('currency_code', sel_code).execute()
                        
                        st.success(f"✅ Currency '{sel_code}' updated successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to update currency: {e}")
