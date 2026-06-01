import streamlit as st
import json
import uuid
from utils.supabase_client import supabase

st.set_page_config(page_title="Admin Migration", page_icon="🔄")
st.title("🔄 Production Data Migration")

st.warning("⚠️ This is a one-time setup tool. It will map your legacy JSON data to the new strict schema.")

# Pre-filled with your provided data for convenience
DEFAULT_JSON = """[
  {"id":"0290c91f-03e1-4310-a6e3-f902b42ecab9","streamer_name":"Looteriya Gaming","email":"looteriya.official@gmail.com","youtube_channel":"https://www.youtube.com/watch?v=VDZqZqRMWHA","upi_id":"riyahaldar86@oksbi","payout_rate":"91","notes":null,"created_at":"2026-01-31 17:38:51.758039+00","updated_at":"2026-06-01 10:27:45.3642+00","payment_cycle":"monthly","next_due_date":"2026-07-01","last_paid_date":"2026-05-01","legal_name":null,"pan_number":null,"bank_name":null,"account_last4":null,"ifsc":null,"tax_status":null}
  // ... (Paste your full JSON array here, or leave as is if already pasted)
]"""

json_input = st.text_area("Paste Creator JSON Data", value=DEFAULT_JSON, height=300)

PREFIX_MAP = {
    "Looteriya Gaming": "lg", "Chiaa": "cg", "lyricsoflove": "lol",
    "SinisterSid": "sns", "Rushandash": "rnd", "sheeshval": "shv",
    "Cheesecake": "chz", "eryx": "ex", "Brigzard": "bz",
    "hunter negi": "hng", "Puchki": "pch", "ShreyPlays": "shp",
    "Dorp Plays": "dp2", "zenichi": "znc", "Demi": "dg",
    "gravenlive": "grv", "GodSeGaming": "gsg", "Tsuki": "tsk",
    "mAcdaking": "mdk", "tejuval": "taj", "Latifa": "gwl",
    "Skar": "skar", "clue less": "cls", "sidd marega": "sm",
    "zeon2k": "z2k", "Wolfy": "wf", "Reyna yadav": "ry",
    "Alpha": "al", "Rizo Plays": "rz", "Zishu": "zs", 
    "ravenclaw": "rvn", "prashant plays": "pp", "Hailer Rahil": "hr", 
    "Waveplayz": "wvp", "Starlight Anya": "sa", "Clumsy God": "cg2", 
    "NYX is Live": "nyx", "Painxfps": "pxf", "flicky": "flk", 
    "KiwiFPS": "kfps", "Kanvi": "knv", "Klurge": "klg", 
    "zuzzie": "zuz", "Notty": "nty", "ish uwu": "iu", 
    "Mr Champion": "mc", "ankit(demo)": "ak", "Slidey Playz": "slp", 
    "suryansh_exd": "sxd", "No Mercy": "nm"
}

if st.button("Start Migration", type="primary"):
    try:
        raw_data = json.loads(json_input)
    except json.JSONDecodeError:
        st.error("Invalid JSON format. Please check your syntax.")
        st.stop()

    creators_to_insert = []
    financial_to_insert = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, item in enumerate(raw_data):
        status_text.text(f"Processing {idx + 1} of {len(raw_data)}...")
        progress_bar.progress((idx + 1) / len(raw_data))
        
        creator_id = item["id"]
        handle = item["streamer_name"].strip()
        code = PREFIX_MAP.get(handle, handle[:3].lower().replace(" ", ""))
        
        notes_parts = []
        if item.get("youtube_channel"): notes_parts.append(f"YouTube: {item['youtube_channel']}")
        if item.get("payout_rate"): notes_parts.append(f"Payout Rate: {item['payout_rate']}%")
        if item.get("payment_cycle"): notes_parts.append(f"Cycle: {item['payment_cycle']}")
        if item.get("next_due_date"): notes_parts.append(f"Next Due: {item['next_due_date'][:10]}")
        if item.get("notes"): notes_parts.append(str(item["notes"]))
            
        notes = " | ".join(notes_parts) if notes_parts else None

        creators_to_insert.append({
            "id": creator_id,
            "creator_code": code,
            "creator_handle": handle,
            "email": item.get("email"),
            "phone_number": item.get("phone_number"),
            "status": "ACTIVE",
            "notes": notes,
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at")
        })

        financial_to_insert.append({
            "id": str(uuid.uuid4()),
            "creator_id": creator_id,
            "legal_name": item.get("legal_name"),
            "pan_number": item.get("pan_number"),
            "upi_id": item.get("upi_id"),
            "bank_name": item.get("bank_name"),
            "account_holder_name": item.get("account_holder_name"),
            "account_number_last4": item.get("account_last4"),
            "ifsc": item.get("ifsc"),
            "tax_verified": bool(item.get("tax_status") == "VERIFIED"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at")
        })

    try:
        status_text.text("Inserting creators...")
        supabase.table("creators").insert(creators_to_insert).execute()
        
        status_text.text("Inserting financial info...")
        supabase.table("creator_financial_info").insert(financial_to_insert).execute()
        
        progress_bar.empty()
        status_text.text("")
        st.success(f"🎉 Migration completed! {len(creators_to_insert)} creators migrated.")
        st.info("You can now safely remove or hide this migration page from your codebase.")
    except Exception as e:
        st.error(f"❌ Migration failed: {e}")
