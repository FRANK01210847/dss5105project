import os, json, time, shutil, re
import streamlit as st
import qrcode
from io import BytesIO
from dotenv import load_dotenv
from utils.rag_utils import build_vectorstore_from_pdf, save_vectorstore
from langchain_community.chat_models import ChatOpenAI
from langchain_community.document_loaders import PyPDFLoader

# ========== 环境变量 ==========
try:
    load_dotenv()
except Exception:
    pass

st.set_page_config(page_title="Landlord Management | Smart Rental", page_icon="🗄️", layout="wide")

# ========== 样式设置 ==========
st.markdown("""
<style>
/* 隐藏侧边栏导航 */
[data-testid="stSidebarNav"], [data-testid="stSidebarHeader"] {
    display: none !important;
    visibility: hidden !important;
}
[data-testid="stSidebar"] { width: 220px !important; }

/* 垃圾桶按钮样式 */
button[aria-label="🗑️"] {
    border: none !important;
    background: transparent !important;
    padding: 6px !important;
    font-size: 24px !important;
    height: 40px !important;
    width: 40px !important;
    display: block !important;
    margin: 0 auto !important;
}
button[aria-label="🗑️"]:hover {
    background: rgba(0,0,0,0.04) !important;
    border-radius: 8px !important;
}
div.stButton {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 0 !important;
}

/* 按钮通用样式 */
div.stButton > button {
    padding: 0.25rem 0.25rem !important;
}
</style>
""", unsafe_allow_html=True)

# ========== 权限检测 ==========
if st.session_state.get("user_role") != "landlords":
    st.warning("Please log in as a 【landlord】.")
    st.switch_page("app.py")

# ========== 顶部栏 ==========
st.markdown("""
<div style="background:#2E8B57;padding:12px 16px;border-radius:12px;margin-bottom:16px;">
  <h3 style="color:#fff;margin:0;">🗄️ Landlord Management System</h3>
</div>
""", unsafe_allow_html=True)

# ========== 侧边栏 ==========
with st.sidebar:
    st.write(f"👋 Welcome: **{st.session_state.get('username','-')}**")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.clear()
        st.switch_page("app.py")

    # 添加导航分隔符
    st.markdown("---")
    
    # 添加页面导航
    if "current_page" not in st.session_state:
        st.session_state.current_page = "existing_leases"
        
    if st.button("📂 Existing Leases", 
                 use_container_width=True,
                 type="primary" if st.session_state.current_page == "existing_leases" else "secondary"):
        st.session_state.current_page = "existing_leases"
        
    if st.button("📤 Upload Contract", 
                 use_container_width=True,
                 type="primary" if st.session_state.current_page == "upload_contract" else "secondary"):
        st.session_state.current_page = "upload_contract"
        
    st.markdown("---")
    
    # OpenAI Key 配置
    if os.getenv("OPENAI_API_KEY"):
        st.success("✅ OpenAI Key is valid")
    else:
        key = st.text_input("OpenAI API Key", type="password")
        if key:
            os.environ["OPENAI_API_KEY"] = key
            st.success("✅ Set successfully")

# ========== 主要内容区域 ==========
if st.session_state.current_page == "upload_contract":
    # ========== 上传合同页面 ==========
    st.markdown("### 📤 Upload Contract")
    c1, c2 = st.columns([1, 3], gap="large")
    
    with c1:
        property_id = st.text_input("🏠 Property ID (Unique)", placeholder="e.g. MSH2025-001")
        tenant_name_input = st.text_input("👤 Tenant Name", placeholder="e.g. John Tan")
        cloud_link = st.text_input("☁️ Cloud Link (Optional)", placeholder="e.g. OneDrive/iCloud Share Link")
        up = st.file_uploader("📄 Upload Tenancy Agreement PDF", type=["pdf"])

        if st.button("Save to Database", type="primary", use_container_width=True):
            os.makedirs("db", exist_ok=True)
            if not (property_id and tenant_name_input and up):
                st.error("Please fill in the Property ID, Tenant Name, and upload the contract.")
            else:
                save_dir = os.path.join("db", property_id)
                os.makedirs(save_dir, exist_ok=True)
                pdf_path = os.path.join(save_dir, "contract.pdf")

                old_pdf_path = os.path.join(save_dir, "contract.pdf")
                if os.path.exists(save_dir) and os.path.exists(old_pdf_path):
                    st.warning("⚠️ Detected existing lease with the same ID. AI is analyzing differences...")

                    try:
                        old_loader = PyPDFLoader(old_pdf_path)
                        old_pages = old_loader.load()
                        old_text = "\n".join(p.page_content for p in old_pages)

                        temp_path = os.path.join(save_dir, "temp_new.pdf")
                        with open(temp_path, "wb") as f:
                            f.write(up.getvalue())

                        new_loader = PyPDFLoader(temp_path)
                        new_pages = new_loader.load()
                        new_text = "\n".join(p.page_content for p in new_pages)

                        llm = ChatOpenAI(
                            model_name="gpt-4o-mini",
                            temperature=0,
                            openai_api_key=os.getenv("OPENAI_API_KEY")
                        )

                        analysis_prompt = f"""
                        Analyze the differences between the old and new rental contracts.
                        Focus on rent amount, lease term, deposit, and other key clauses.

                        Old contract:
                        {old_text}

                        New contract:
                        {new_text}

                        Output a clear English comparison report.
                        """

                        with st.spinner("AI is analyzing contract differences..."):
                            differences_prompt = f"""
                            Compare the OLD and NEW rental contracts below and output ONLY the items that changed between the two versions.
                            Return the changed items in the EXACT order below (omit any field that did not change):
                            1) LANDLORD NAME
                            2) TENANT NAME
                            3) MONTHLY RENT
                            4) SECURITY DEPOSIT
                            5) LEASE TERM / START / END
                            6) PROPERTY ADDRESS / PREMISES
                            7) UTILITIES
                            8) REPAIRS AND MAINTENANCE
                            9) TERMINATION / PENALTIES
                            10) ADDITIONAL CLAUSES

                            For each change, provide a single concise bullet point in this format:
                            - FIELD: Old: <old value> -> New: <new value>

                            If a field cannot be precisely extracted, describe the change in one short sentence.
                            If there are no material differences, output exactly: No material differences detected.
                            Do not include any extra explanation or unchanged text.

                            OLD CONTRACT:
                            {old_text}

                            NEW CONTRACT:
                            {new_text}
                            """

                            try:
                                diffs = llm.predict(differences_prompt).strip()
                            except Exception:
                                diffs = llm.predict(analysis_prompt)

                            # Try to auto-clean the diffs into well-formatted Markdown
                            try:
                                llm_fix = ChatOpenAI(
                                    model_name="gpt-4o-mini",
                                    temperature=0,
                                    openai_api_key=os.getenv("OPENAI_API_KEY")
                                )
                                fix_prompt = f"""
                                The following contract difference report may contain formatting issues (missing spaces, malformed punctuation).
                                Reformat it into a clean Markdown bullet list. Preserve the meaning exactly but fix spacing, punctuation, and ensure each change is a separate bullet.

                                Report:
                                {diffs}
                                """
                                cleaned = llm_fix.predict(fix_prompt).strip()
                            except Exception:
                                cleaned = None

                            st.session_state['last_diffs'] = cleaned or diffs

                        os.remove(temp_path)

                    except Exception as e:
                        st.error(f"❌ Contract analysis failed: {str(e)}")
                else:
                    st.info("🆕 This is a new contract. No previous version found for comparison.")

                with open(pdf_path, "wb") as f:
                    f.write(up.getvalue())

                # Extract tenant name
                tenant_final = None
                landlord_final = st.session_state.get("username") or None

                # Save vector store
                vectorstore = build_vectorstore_from_pdf(pdf_path)
                save_vectorstore(vectorstore, save_dir)

                # Save metadata
                meta = {
                    "tenant_name": tenant_name_input,
                    "cloud_link": cloud_link,
                    "landlord": landlord_final,
                    "property_id": property_id,
                    "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
                }

                meta_path = os.path.join(save_dir, "metadata.json")
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)

                st.success("✅ Contract uploaded successfully!")

    with c2:
        # If diffs exist in session state, show a compact expander button so user can view full differences on demand
        if st.session_state.get('last_diffs'):
            with st.expander("📄 View full report — Contract Differences", expanded=False):
                report = st.session_state.get('last_diffs')
                # Render the differences directly (only changed items are present, in the requested order)
                st.markdown(report)

else:  # existing_leases page
    # ========== 现有租约页面 ==========
    st.markdown("### 📂 Existing Leases")
    if "delete_confirm" not in st.session_state:
        st.session_state.delete_confirm = None

    rows = []
    os.makedirs("db", exist_ok=True)
    for name in sorted(os.listdir("db")):
        p = os.path.join("db", name)
        if os.path.isdir(p):
            meta_path = os.path.join(p, "metadata.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        m = json.load(f)
                    # Format rent period
                    rent_period = "—"
                    if m.get("lease_start") and m.get("lease_end"):
                        rent_period = f"{m['lease_start']} to {m['lease_end']}"
                    elif m.get("lease_term_months"):
                        rent_period = f"{m.get('lease_term_months')} months"
                    
                    # Order: ID, Tenant, Monthly Rent, Rent Period, Address, Last Updated, Cloud Link
                    rows.append([
                        name,  # ID
                        m.get("tenant_name", "-"),  # Tenant
                        m.get("monthly_rent", "?"),  # Monthly Rent
                        rent_period,  # Rent Period
                        m.get("property_address", "—"),  # Address
                        m.get("last_updated", "?"),  # Last Updated
                        "✅" if m.get("cloud_link") else "❌",  # Cloud Link
                    ])
                except json.JSONDecodeError:
                    st.warning(f"⚠️ Skipped corrupted metadata file: {meta_path}")

    if rows:
        # Adjust column widths: balance Address and Cloud Link so Cloud Link isn't squeezed
        header_cols = st.columns([0.8, 1.4, 1, 1, 1.6, 1, 0.9, 0.8])
        headers = ["ID", "Tenant", "Monthly Rent", "Rent Period", "Address", "Last Updated", "Cloud Link", "Delete"]
        for i, h in enumerate(headers):
            with header_cols[i]:
                st.markdown(f"**{h}**")

        st.markdown("---")

        for r in rows:
            cols = st.columns([0.8, 1.4, 1, 1, 1.6, 1, 0.9, 0.8])
            for i, v in enumerate(r):
                with cols[i]:
                    st.text(v)
            # Add delete button centered in the last column
            with cols[-1]:
                if st.button(
                    "🗑️", 
                    key=f"del_{r[0]}",
                    help=f"Delete lease {r[0]}",
                    use_container_width=False
                ):
                    st.session_state.delete_confirm = r[0]

        if st.session_state.delete_confirm:
            contract_id = st.session_state.delete_confirm
            st.warning(f"⚠️ Are you sure you want to delete lease {contract_id}? This action cannot be undone!")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Confirm Delete"):
                    try:
                        shutil.rmtree(os.path.join("db", contract_id))
                        st.success(f"✅ Deleted lease: {contract_id}")
                        st.session_state.delete_confirm = None
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to delete: {str(e)}")
            with col2:
                if st.button("❌ Cancel"):
                    st.session_state.delete_confirm = None
                    st.rerun()
    else:
        st.info("No leases found. Please upload a lease first.")