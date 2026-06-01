# utils/helpers.py
import datetime
from zoneinfo import ZoneInfo

# Define IST Timezone (Asia/Kolkata is UTC+5:30)
IST = ZoneInfo("Asia/Kolkata")

def format_inr(val):
    """Safely formats paise/cents into INR Rupees."""
    if val is None or val == 0: return "₹0.00"
    try: return f"₹{float(val)/100:.2f}"
    except (ValueError, TypeError): return "₹0.00"

def to_ist(dt_val):
    """Converts any UTC datetime/ISO string to a readable IST string."""
    if not dt_val: return "N/A"
    try:
        if isinstance(dt_val, str):
            dt = datetime.datetime.fromisoformat(dt_val)
        else:
            dt = dt_val
            
        # If naive, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
            
        return dt.astimezone(IST).strftime('%d/%m/%Y %H:%M IST')
    except Exception:
        return str(dt_val)
