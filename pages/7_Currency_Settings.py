import streamlit as st
import pandas as pd
import datetime
from utils.supabase_client import supabase
from utils.auth import require_auth

require_auth()

st.set_page_config(page_title="Currency Settings", page_icon="💱", layout="wide")
st.title("💱 Currency & Exchange Rate Settings")

# ==============================================================================
# 1. AGGRESSIVE DEBUG & DATA FETCHING
# ==============================================================================
st.markdown("### 🔍 System Debug")
df_rates = pd.DataFrame()
table_used = ""

try:
    # Attempt 1: Try 'currency_rates'
    res1 = supabase.table('currency_rates').select('*').execute()
    st.write(f"📡 Query to 'currency_rates' returned: **{len(res1.data) if res1.data else 0} rows**")
    
    if res1.data and len(res1.data) > 0:
        df_rates = pd.DataFrame(res1.data)
        table_used = "currency_rates"
        st.success("✅ Successfully found data in 'currency_rates'!")
    else:
        # Attempt 2: Try 'currencies' just in case the name is different
        st.info("Trying fallback table name 'currencies'...")
        res2 = supabase.table('currencies').select('*').execute()
        st.write(f"📡 Query to 'currencies' returned: **{len(res2.data) if res2.data else 0} rows**")
        
        if res2.data and len(res2.data) > 0:
            df_rates = pd.DataFrame(res2.data)
            table_used = "currencies"
            st.success("✅ Successfully found data in 'currencies'!")
        else:
            st.error("⚠️ **CRITICAL:** Both tables returned 0 rows. This means either the table is empty, the name is different, or RLS is blocking the 'anon' key.")
            
except Exception as e:
    st.error(f"❌ Database query failed completely: {e}")

st.divider()

# ==============================================================================
# 2. BULLETPROOF UI RENDERING
# ==============================================================================
st.markdown("### 📊 Current Exchange Rates")

if df_rates.empty:
    st.warning("No currency data could be loaded. Please check the Debug info above.")
else:
    # Show a snippet of the raw data so we know it's working
    with st.expander("View Raw Data Loaded"):
        st.json(df_rates.head(2).to_dict(orient="records"))

    # Safely identify the exact column names from your database schema
    code_col = 'currency_code' if 'currency_code' in df_rates.columns else ('code' if 'code' in df_rates.columns else 'currency')
    rate_col = 'rate_to_inr' if 'rate_to_inr' in df_rates.columns else ('exchange_rate_to_inr' if 'exchange_rate_to_inr' in df_rates.columns else 'rate')
    
    st.markdown(f"*(Detected columns: Code=`{code_col}`, Rate=`{rate_col}`)*")

    display_df = df_rates.copy()
    
    # Ensure required columns exist for display
    if rate_col not in display_df.columns:
        display_df[rate_col] = 1.0
        
    display_df['Rate (1 Foreign = X INR)'] = display_df[rate_col].apply(
        lambda x: f"₹{float(x):,.2f}" if pd.notnull(x) else "N/A"
    )
    
    cols_to_show = [code_col, 'Rate (1 Foreign = X INR)']
    if 'updated_at' in display_df.columns:
        cols_to_show.append('updated_at')
        
    st.dataframe(
        display_df[cols_to_show], 
        width="stretch", 
        hide_index=True
    )

st.divider()

# ==============================================================================
# 3. UI: ADD / EDIT CURRENCY
# ==============================================================================
st.markdown("### ⚙️ Manage Currencies")

tab_add, tab_edit = st.tabs(["➕ Add New Currency", "✏️ Edit Existing Currency"])

with tab_add:
    with st.form("add_currency_form"):
        c1, c2 = st.columns(2)
        with c1:
            new_code = st.text_input("Currency Code (e.g., USD, EUR)", max_chars=3).strip().upper()
        with c2:
            new_rate = st.number_input("Exchange Rate (1 Foreign Unit = ? INR)", min_value=0.01, step=0.01, format="%.4f")
            
        submitted_add = st.form_submit_button("💾 Add Currency", type="primary", width="stretch")
        
        if submitted_add:
            if not new_code:
                st.error("Currency code is required.")
            elif not df_rates.empty and code_col in df_rates.columns and new_code in df_rates[code_col].astype(str).values:
                st.error(f"Currency '{new_code}' already exists.")
            else:
                try:
                    # Use the table name that actually worked
                    target_table = table_used if table_used else 'currency_rates'
                    
                    insert_data = {
                        "currency_code": new_code,
                        "rate_to_inr": float(new_rate),
                        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                    }
                    
                    # If the working table was 'currencies', adapt the keys
                    if target_table == 'currencies' and 'currency_code' not in df_rates.columns:
                        insert_data = {"code": new_code, "rate": float(new_rate)}

                    supabase.table(target_table).insert(insert_data).execute()
                    st.success(f"✅ Currency '{new_code}' added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to add currency: {e}")

with tab_edit:
    if df_rates.empty or code_col not in df_rates.columns:
        st.warning("No currencies available to edit.")
    else:
        existing_codes = df_rates[code_col].dropna().astype(str).unique().tolist()
        
        if not existing_codes:
            st.warning("No valid currency codes found to edit.")
        else:
            with st.form("edit_currency_form"):
                sel_code = st.selectbox("Select Currency to Edit", options=existing_codes)
                
                current_row = df_rates[df_rates[code_col] == sel_code].iloc[0]
                current_rate = float(current_row.get(rate_col, 1.0))
                
                c1, c2 = st.columns(2)
                with c1:
                    edit_rate = st.number_input("New Exchange Rate", min_value=0.01, step=0.01, value=current_rate, format="%.4f")
                
                submitted_edit = st.form_submit_button("💾 Update Currency", type="primary", width="stretch")
                
                if submitted_edit:
                    try:
                        target_table = table_used if table_used else 'currency_rates'
                        
                        update_data = {
                            "rate_to_inr": float(edit_rate),
                            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                        }
                        
                        if target_table == 'currencies' and rate_col != 'rate_to_inr':
                            update_data = {"rate": float(edit_rate)}

                        supabase.table(target_table).update(update_data).eq(code_col, sel_code).execute()
                        
                        st.success(f"✅ Currency '{sel_code}' updated successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to update currency: {e}")
