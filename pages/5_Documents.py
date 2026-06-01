import streamlit as st
from utils.supabase_client import supabase
import uuid

st.set_page_config(page_title="Documents", page_icon="📄")
st.title("📄 Document Management")

if 'selected_creator_id' not in st.session_state:
    st.warning("Please select a creator from the Creator List first to manage documents.")
    st.stop()

creator_id = st.session_state['selected_creator_id']
creator = supabase.table('creators').select('creator_handle').eq('id', creator_id).execute().data[0]
st.subheader(f"Managing documents for @{creator['creator_handle']}")

# Upload Section
st.markdown("### Upload New Document")
doc_type = st.selectbox("Document Type", ["PAN Card", "Cancelled Cheque", "Bank Proof"])
uploaded_file = st.file_uploader("Choose a file", type=["pdf", "jpg", "jpeg", "png"])

if st.button("Upload Document"):
    if not uploaded_file:
        st.error("Please select a file to upload.")
    else:
        # Clean filename
        file_ext = uploaded_file.name.split('.')[-1]
        file_path = f"{creator_id}/{doc_type.lower().replace(' ', '_')}.{file_ext}"
        
        try:
            # Upload to Storage
            supabase.storage.from_("creator-documents").upload(
                file_path, 
                uploaded_file.getvalue(), 
                file_options={"content-type": uploaded_file.type, "upsert": "true"}
            )
            
            # Save metadata
            supabase.table('creator_documents').insert({
                "creator_id": creator_id,
                "document_type": doc_type,
                "file_url": file_path,
                "uploaded_by": "admin"
            }).execute()
            
            st.success("Document uploaded successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Upload failed: {e}")

# View Documents Section
st.markdown("### Uploaded Documents")
docs = supabase.table('creator_documents').select('*').eq('creator_id', creator_id).execute().data

if not docs:
    st.info("No documents uploaded yet. Use the form above to upload.")
else:
    for doc in docs:
        with st.expander(f"{doc['document_type']} (Uploaded: {doc['uploaded_at'][:10]})"):
            try:
                # Generate signed URL for private file
                signed_url_res = supabase.storage.from_("creator-documents").create_signed_url(doc['file_url'], 3600)
                file_url = signed_url_res.data['signedURL']
                
                if doc['file_url'].endswith('.pdf'):
                    st.markdown(f"[📄 Download PDF]({file_url})")
                else:
                    st.image(file_url)
                    
            except Exception as e:
                st.error(f"Could not retrieve file: {e}")
