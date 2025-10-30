import os, json, time, shutil
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

# ========== 隐藏侧边栏导航 ==========
st.markdown("""
    <style>
    [data-testid="stSidebarNav"], [data-testid="stSidebarHeader"] {
        display: none !important;
        visibility: hidden !important;
    }
    [data-testid="stSidebar"] { width: 220px !important; }
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

    if os.getenv("OPENAI_API_KEY"):
        st.success("✅ OpenAI Key is valid")
    else:
        key = st.text_input("OpenAI API Key", type="password")
        if key:
            os.environ["OPENAI_API_KEY"] = key
            st.success("✅ Set successfully")

# ========== 上传合同部分 ==========
st.markdown("### Upload Contract → Database")
c1, c2 = st.columns([1.2, 1.8], gap="large")

with c1:
    property_id = st.text_input("🏠 Property ID (Unique)", placeholder="e.g. MSH2025-001")
    tenant_name = st.text_input("👤 Tenant Name", placeholder="e.g. Ken")
    version_note = st.text_input("📝 Version Note (Optional)", placeholder="e.g. First Version / Adjusted Deposit")
    cloud_link = st.text_input("☁️ Cloud Link (Optional)", placeholder="e.g. OneDrive/iCloud Share Link")
    up = st.file_uploader("📄 Upload Tenancy Agreement PDF", type=["pdf"])

    if st.button("Save to Database", type="primary", use_container_width=True):
        os.makedirs("db", exist_ok=True)
        if not (property_id and up):
            st.error("Please fill in the Property ID and upload the contract.")
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
                        analysis = llm.predict(analysis_prompt)
                        st.markdown("### 📄 Contract Difference Analysis")
                        st.markdown(analysis)

                    os.remove(temp_path)

                except Exception as e:
                    st.error(f"❌ Contract analysis failed: {str(e)}")
            else:
                st.info("🆕 This is a new contract. No previous version found for comparison.")

            # 保存当前 PDF
            with open(pdf_path, "wb") as f:
                f.write(up.getvalue())

            # ---------- 自动提取租金 ----------
            try:
                loader = PyPDFLoader(pdf_path)
                pages = loader.load()
                text = "\n".join(p.page_content for p in pages)

                llm = ChatOpenAI(
                    model_name="gpt-4o-mini",
                    temperature=0,
                    openai_api_key=os.getenv("OPENAI_API_KEY")
                )

                rent_prompt = f"""
                The following text is from a rental contract.
                Please extract ONLY the monthly rent amount in SGD.
                Example outputs: "S$7500", "SGD 5800", "N/A" if not found.
                Contract text:
                {text}
                """

                with st.spinner("🔍 Extracting monthly rent from contract..."):
                    rent_extracted = llm.predict(rent_prompt).strip()
                    if not rent_extracted or "n/a" in rent_extracted.lower():
                        rent_extracted = "N/A"
                        st.warning("⚠️ Monthly rent not found in the document.")
                    else:
                        st.success(f"✅ Detected monthly rent: {rent_extracted}")
            except Exception as e:
                st.error(f"❌ Failed to extract rent: {e}")
                rent_extracted = "N/A"

            # ---------- 构建向量数据库 ----------
            with st.spinner("Parsing and building index..."):
                vs = build_vectorstore_from_pdf(up, openai_api_key=os.getenv("OPENAI_API_KEY"))
                save_vectorstore(vs, save_dir)

            # ---------- 生成二维码 ----------
            qr_filename = ""
            if cloud_link:
                try:
                    qr = qrcode.QRCode(
                        version=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_L,
                        box_size=10,
                        border=4,
                    )
                    qr.add_data(cloud_link)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    qr_filename = "contract_qr.png"
                    img.save(os.path.join(save_dir, qr_filename))
                except Exception as e:
                    st.warning(f"Failed to generate QR code: {str(e)}")

            # ---------- 保存元数据 ----------
            old_meta_path = os.path.join(save_dir, "metadata.json")
            old_version_time = None
            if os.path.exists(old_meta_path):
                try:
                    with open(old_meta_path, "r", encoding="utf-8") as f:
                        old_meta = json.load(f)
                        old_version_time = old_meta.get("last_updated")
                except Exception:
                    pass

            meta = {
                "property_id": property_id,
                "tenant_name": tenant_name,
                "monthly_rent": rent_extracted,
                "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "version_note": version_note or "v1",
                "cloud_link": cloud_link or "",
                "qr_code": qr_filename or "",
                "previous_version": old_version_time,
            }

            with open(os.path.join(save_dir, "metadata.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            st.success(f"✅ Successfully saved: {property_id}")
            col1, col2 = st.columns([2, 1])
            with col1:
                st.json(meta)
            if qr_filename:
                with col2:
                    st.image(os.path.join(save_dir, qr_filename), caption="Contract Cloud Link QR Code")

# ========== 右侧：已有合同列表 ==========
with c2:
    st.markdown("#### 📂 Existing Leases")
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
                    rows.append([
                        name,
                        m.get("tenant_name", "?"),
                        m.get("monthly_rent", "?"),
                        m.get("last_updated", "?"),
                        m.get("version_note", "-"),
                        "✅" if m.get("cloud_link") else "❌",
                    ])
                except json.JSONDecodeError:
                    st.warning(f"⚠️ Skipped corrupted metadata file: {meta_path}")

    if rows:
        header_cols = st.columns([1.2, 1, 1, 1.2, 1, 0.8])
        headers = ["Tenant ID", "Tenant", "Monthly Rent", "Last Updated", "Version Note", "Cloud Link"]
        for i, h in enumerate(headers):
            with header_cols[i]:
                st.markdown(f"**{h}**")

        st.markdown("---")

        for r in rows:
            cols = st.columns([1.2, 1, 1, 1.2, 1, 0.8])
            for i, v in enumerate(r):
                with cols[i]:
                    st.text(v)

            if st.button("🗑️", key=f"del_{r[0]}", help=f"Delete lease {r[0]}"):
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
