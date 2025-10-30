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
# Simplified heading
st.markdown("### Upload Contract")
# Custom CSS: make the trashcan button borderless and slightly larger (targets the button by aria-label)
st.markdown("""
<style>
/* Larger, borderless trashcan button; centered via margins */
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
/* Ensure the button's parent container centers its content (helps vertical/horizontal centering) */
div.stButton {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 0 !important;
}

/* Narrow global button padding to reduce rounded-rectangle appearance */
div.stButton > button {
    padding: 0.25rem 0.25rem !important;
}
</style>
""", unsafe_allow_html=True)
# Give the Existing Leases column more width (right side) to reduce crowding
c1, c2 = st.columns([1, 3], gap="large")

with c1:
    property_id = st.text_input("🏠 Property ID (Unique)", placeholder="e.g. MSH2025-001")
    tenant_name_input = st.text_input("👤 Tenant Name", placeholder="e.g. John Tan")
    cloud_link = st.text_input("☁️ Cloud Link (Optional)", placeholder="e.g. OneDrive/iCloud Share Link")
    up = st.file_uploader("📄 Upload Tenancy Agreement PDF", type=["pdf"])

    if st.button("Save to Database", type="primary", use_container_width=True):
        os.makedirs("db", exist_ok=True)
        # Require tenant name as a mandatory field
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
                        # Ask the model to return ONLY the differences between the two contracts.
                        # Output must be concise bullet points and must NOT include any unchanged sections.
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
                            # fallback to the full analysis if diff-only prompt fails
                            diffs = llm.predict(analysis_prompt)

                        # Try to auto-clean the diffs into well-formatted Markdown using the LLM
                        cleaned = None
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

                        # Save the cleaned version if available, otherwise save the raw diffs
                        st.session_state['last_diffs'] = cleaned or diffs
                        st.info("✅ Comparison ready. Click 'View full report' on the right to view the differences.")

                    os.remove(temp_path)

                except Exception as e:
                    st.error(f"❌ Contract analysis failed: {str(e)}")
            else:
                st.info("🆕 This is a new contract. No previous version found for comparison.")

            # 保存当前 PDF
            with open(pdf_path, "wb") as f:
                f.write(up.getvalue())

            # ---------- 自动提取租金 ----------
            # initialize defaults so metadata is always populated even if extraction fails
            tenant_final = None
            landlord_final = st.session_state.get("username") or None
            deposit_final = "N/A"
            lease_months_final = None
            lease_start = None
            lease_end = None
            prop_addr_final = ""

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

                # ---------- 更丰富的信息提取（尝试以 JSON 输出） ----------
                extract_prompt = f"""
                Extract the following fields from the contract text and output a JSON object ONLY.
                Fields: monthly_rent, lease_start (YYYY-MM-DD or null), lease_end (YYYY-MM-DD or null), lease_term_months (integer or null), deposit_amount (SGD, like "S$1200" or null), landlord_name (string or null), tenant_name (string or null), property_address (string or null).

                If a field cannot be found, use null. Do not output any explanatory text.

                Contract text:
                {text}
                """

                with st.spinner("🔍 Extracting structured metadata from contract..."):
                    try:
                        extracted_raw = llm.predict(extract_prompt).strip()
                        # try to parse JSON directly
                        extracted_json = None
                        try:
                            extracted_json = json.loads(extracted_raw)
                        except Exception:
                            # attempt to find a JSON substring
                            jmatch = re.search(r"\{[\s\S]*\}", extracted_raw)
                            if jmatch:
                                try:
                                    extracted_json = json.loads(jmatch.group(0))
                                except Exception:
                                    extracted_json = None

                        if extracted_json is None:
                            raise ValueError("LLM did not return valid JSON")

                        lease_start = extracted_json.get("lease_start")
                        lease_end = extracted_json.get("lease_end")
                        lease_term_months = extracted_json.get("lease_term_months")
                        deposit_amount = extracted_json.get("deposit_amount")
                        landlord_name_ex = extracted_json.get("landlord_name")
                        tenant_name_ex = extracted_json.get("tenant_name")
                        property_address_ex = extracted_json.get("property_address")
                    except Exception:
                        # 回退：使用简单的正则从文本中抽取 deposit 与租期信息
                        lease_start = None
                        lease_end = None
                        lease_term_months = None
                        deposit_amount = None
                        landlord_name_ex = None
                        tenant_name_ex = None
                        property_address_ex = None

                        # deposit: look for 'deposit' near an amount
                        dmatch = re.search(r"deposit[\s:\-\n\w\W]{0,60}?S\$\s?([\d,]{2,7})", text, re.IGNORECASE)
                        if not dmatch:
                            dmatch = re.search(r"deposit[\s:\-\n\w\W]{0,60}?\$\s?([\d,]{2,7})", text, re.IGNORECASE)
                        if dmatch:
                            deposit_amount = f"S${dmatch.group(1).replace(',', '')}"

                        # lease term months: look for 'month' or 'months' near numbers
                        tmatch = re.search(r"(\d{1,2})\s*(?:months|month|months'?)", text, re.IGNORECASE)
                        if tmatch:
                            try:
                                lease_term_months = int(tmatch.group(1))
                            except Exception:
                                lease_term_months = None

                        # attempt to find landlord name (look for 'Landlord' label)
                        lmatch = re.search(r"Landlord[:\s]+([A-Z][a-zA-Z\s,.'-]{2,60})", text)
                        if lmatch:
                            landlord_name_ex = lmatch.group(1).strip()

                        # property address: look for Address: label
                        amatch = re.search(r"Address[:\s]+([\w\d\s,.-]{5,200})", text)
                        if amatch:
                            property_address_ex = amatch.group(1).strip()

                # normalize values
                # Prefer explicitly entered tenant name; fall back to extracted name or None
                tenant_final = tenant_name_input or tenant_name_ex or None
                landlord_final = landlord_name_ex or st.session_state.get("username") or None
                deposit_final = deposit_amount or "N/A"
                lease_months_final = lease_term_months or None
                prop_addr_final = property_address_ex or None
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
                "tenant_name": tenant_final,
                "landlord_name": landlord_final or st.session_state.get("username"),
                "property_address": prop_addr_final or "",
                "monthly_rent": rent_extracted,
                "deposit": deposit_final,
                "lease_start": lease_start,
                "lease_end": lease_end,
                "lease_term_months": lease_months_final,
                "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
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
    # If diffs exist in session state, show a compact expander button so user can view full differences on demand
    if st.session_state.get('last_diffs'):
        with st.expander("📄 View full report — Contract Differences", expanded=False):
            report = st.session_state.get('last_diffs')
            # Render the differences directly (only changed items are present, in the requested order)
            st.markdown(report)

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
                # Center the trashcan and make the button take more space by using a wider middle column
                inner = st.columns([2, 5, 2])
                with inner[1]:
                    # use_container_width=False so the button keeps the squared size from CSS but is centered by margin:auto
                    if st.button("🗑️", key=f"del_{r[0]}", help=f"Delete lease {r[0]}", use_container_width=False):
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
