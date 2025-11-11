import os, json, time, shutil, re
import streamlit as st
import qrcode
import pandas as pd
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

# ========== 页面状态初始化 ==========
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "existing_leases"
    # pagination defaults
if "existing_page" not in st.session_state:
    st.session_state["existing_page"] = 1
if "listings_page" not in st.session_state:
    st.session_state["listings_page"] = 1

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
    
    # 添加页面导航按钮（垂直排列）
    if st.button("📂 Existing Leases", 
                 key="nav_leases",
                 use_container_width=True,
                 type="primary" if st.session_state.current_page == "existing_leases" else "secondary"):
        st.session_state.current_page = "existing_leases"
        st.rerun()

    if st.button("📤 Upload Contract", 
                 key="nav_upload",
                 use_container_width=True,
                 type="primary" if st.session_state.current_page == "upload_contract" else "secondary"):
        st.session_state.current_page = "upload_contract"
        st.rerun()

    if st.button("🏘️ Available Listings", 
                 key="nav_listings",
                 use_container_width=True,
                 type="primary" if st.session_state.current_page == "available_listings" else "secondary"):
        st.session_state.current_page = "available_listings"
        st.rerun()
            
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
    c1, c2 = st.columns([1, 1], gap="large")
    
    property_id = None
    tenant_username_input = None
    cloud_link = None
    up = None
    
    with c1:
        property_id = st.text_input("🏠 Property ID (Unique)", placeholder="e.g. E0001")
        tenant_username_input = st.text_input("👤 Tenant Username", placeholder="e.g. Donald Trump")
        cloud_link = st.text_input("☁️ Cloud Link (Optional)", placeholder="e.g. Dropbox Share Link")
        up = st.file_uploader("📄 Upload Tenancy Agreement PDF", type=["pdf"])
        st.button("Save to Database", type="primary", use_container_width=True, key="save_btn")

    with c2:
        if st.session_state.get("save_btn"):
            os.makedirs("db", exist_ok=True)
            if not (property_id and tenant_username_input and up):
                st.error("Please fill in the Property ID, Tenant Username, and upload the contract.")
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
                    st.info("🆕 This is a new contract. Analyzing contract details...")
                    
                    # Save the new contract first
                    with open(pdf_path, "wb") as f:
                        f.write(up.getvalue())
                    
                    # Load and analyze the new contract
                    try:
                        new_loader = PyPDFLoader(pdf_path)
                        new_pages = new_loader.load()
                        new_text = "\n".join(p.page_content for p in new_pages)

                        llm = ChatOpenAI(
                            model_name="gpt-4o-mini",
                            temperature=0,
                            openai_api_key=os.getenv("OPENAI_API_KEY")
                        )

                        analysis_prompt = f"""
                        Extract the following information from the rental contract. For each field, if the information is not found, write "Not specified".
                        Return in this exact format, keeping the numbering:

                        1) LANDLORD NAME: <extracted info>
                        2) TENANT NAME: <extracted info>
                        3) MONTHLY RENT: <extracted info>
                        4) SECURITY DEPOSIT: <extracted info>
                        5) LEASE TERM / START / END: <extracted info>
                        6) PROPERTY ADDRESS / PREMISES: <extracted info>
                        7) UTILITIES: <extracted info>
                        8) REPAIRS AND MAINTENANCE: <extracted info>
                        9) TERMINATION / PENALTIES: <extracted info>
                        10) ADDITIONAL CLAUSES: <extracted info>

                        CONTRACT TEXT:
                        {new_text}
                        """

                        with st.spinner("AI is analyzing the contract..."):
                            contract_info = llm.predict(analysis_prompt).strip()
                            st.markdown("### 📄 Contract Summary")
                            st.markdown(contract_info)

                    except Exception as e:
                        st.error(f"❌ Contract analysis failed: {str(e)}")

                with open(pdf_path, "wb") as f:
                    f.write(up.getvalue())

                # Extract tenant name
                tenant_final = None
                landlord_final = st.session_state.get("username") or None

                # Save vector store
                vectorstore = build_vectorstore_from_pdf(pdf_path)
                save_vectorstore(vectorstore, save_dir)

                # 解析合同信息用于保存
                contract_data = {}
                try:
                    # 如果是新合同，从contract_info中提取信息
                    if 'contract_info' in locals() and contract_info:
                        lines = contract_info.split('\n')
                        for line in lines:
                            if ': ' in line:
                                key, value = line.split(': ', 1)
                                key = key.split(') ', 1)[1] if ') ' in key else key
                                contract_data[key.lower()] = value

                    # 如果是更新的合同，从diffs中提取最新信息
                    elif 'diffs' in locals() and diffs:
                        for line in diffs.split('\n'):
                            if '-> New:' in line:
                                key = line.split(':')[0].strip('- ')
                                value = line.split('-> New:')[1].strip()
                                contract_data[key.lower()] = value
                except Exception:
                    pass

                # Save metadata
                meta = {
                    "tenant_username": tenant_username_input,
                    "cloud_link": cloud_link,
                    "landlord": contract_data.get('landlord name', landlord_final),
                    "tenant_name": contract_data.get('tenant name', 'Not specified'),
                    "monthly_rent": contract_data.get('monthly rent', 'Not specified'),
                    "lease_term": contract_data.get('lease term / start / end', 'Not specified'),
                    "property_address": contract_data.get('property address / premises', 'Not specified'),
                    "property_id": property_id,
                    "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
                }

                meta_path = os.path.join(save_dir, "metadata.json")
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)

                # Also save tenant -> property mapping into db/contracts.json
                try:
                    contracts_path = os.path.join("db", "contracts.json")
                    contracts = {}
                    if os.path.exists(contracts_path):
                        try:
                            with open(contracts_path, "r", encoding="utf-8") as cf:
                                contracts = json.load(cf)
                        except Exception:
                            contracts = {}

                    if tenant_username_input:
                        # normalize existing entries into list form
                        existing = contracts.get(tenant_username_input)
                        if existing:
                            # If stored as single string, convert to list
                            if isinstance(existing, str):
                                if existing != property_id:
                                    contracts[tenant_username_input] = [existing, property_id]
                            elif isinstance(existing, list):
                                if property_id not in existing:
                                    existing.append(property_id)
                                    contracts[tenant_username_input] = existing
                        else:
                            # New entry: store as list for future-proofing
                            contracts[tenant_username_input] = [property_id]

                    with open(contracts_path, "w", encoding="utf-8") as cf:
                        json.dump(contracts, cf, ensure_ascii=False, indent=2)
                except Exception as e:
                    st.warning(f"⚠️ Failed to save tenant->contract mapping: {e}")

                # Generate QR code for the contract (prefer cloud link when available)
                try:
                    qr_content = cloud_link
                    qr_img = qrcode.make(qr_content)
                    qr_path = os.path.join(save_dir, "contract_qr.png")
                    qr_img.save(qr_path)
                except Exception as e:
                    # Non-fatal: warn user but continue
                    st.warning(f"⚠️ Failed to generate QR code: {e}")

                # 在成功上传后，如果这是一个新合同，清除之前的合同对比信息
                if not os.path.exists(old_pdf_path):
                    if 'last_diffs' in st.session_state:
                        del st.session_state['last_diffs']
                st.success("✅ Contract uploaded successfully!")

        
        # 只有在有合同对比时才显示对比报告
        if st.session_state.get('last_diffs'):
            with st.expander("📄 View full report — Contract Differences", expanded=False):
                report = st.session_state.get('last_diffs')
                # Render the differences directly (only changed items are present, in the requested order)
                st.markdown(report)

elif st.session_state.current_page == "existing_leases":
    # ========== 现有租约页面 ==========
    st.markdown("### 📂 Existing Leases")
    if "delete_confirm" not in st.session_state:
        st.session_state.delete_confirm = None

    # Initialize variables
    rows = []  # Initialize rows as empty list
    rows_data = []
    
    # Initialize filter states if not exists
    if 'leases_filters' not in st.session_state:
        st.session_state.leases_filters = {}
    if 'leases_sort' not in st.session_state:
        st.session_state.leases_sort = {'column': None, 'direction': None}

    os.makedirs("db", exist_ok=True)
    # map of contract ID -> cloud link (raw URL) for rendering clickable ID
    leases_cloud_map = {}
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
                    
                    # store cloud link for this lease
                    leases_cloud_map[name] = m.get("cloud_link")

                    # Add to rows data
                    rows_data.append({
                        'ID': name,
                        'Tenant Username': m.get("tenant_username", "-"),
                        'Landlord': m.get("landlord", "-"),
                        'Tenant': m.get("tenant_name", "-"),
                        'Monthly Rent': m.get("monthly_rent", "?"),
                        'Rent Period': m.get("lease_term", "—"),
                        'Address': m.get("property_address", "—"),
                        'Last Updated': m.get("last_updated", "?"),
                        'Cloud Link': "✅" if m.get("cloud_link") else "❌"
                    })
                except json.JSONDecodeError:
                    st.warning(f"⚠️ Skipped corrupted metadata file: {meta_path}")
    
    if rows_data:
        df = pd.DataFrame(rows_data)
        
        # Create filter controls
        st.markdown("#### 🔍 Filters & Sort")
        filter_cols = st.columns(5)  # Adjust number based on your needs
        
        # Only add filters for specified columns
        filter_columns = ['ID', 'Tenant Username', 'Landlord', 'Tenant', 'Cloud Link']
        
        for i, col in enumerate(filter_columns):
            with filter_cols[i]:  # Use direct index since we have exactly 5 columns
                # Get unique values for the column
                unique_vals = sorted(df[col].unique().tolist())
                
                # Create multiselect filter with search
                selected = st.multiselect(
                    f"Filter {col}",
                    options=unique_vals,
                    default=[],
                    key=f"lease_filter_{col}",
                    placeholder=f"Search {col}..."  # Add search placeholder
                )
                
                # Store filter selection
                st.session_state.leases_filters[col] = selected
                
                # Add sort buttons
                sort_col = st.radio(
                    f"Sort {col}",
                    ["None", "↑", "↓"],
                    horizontal=True,
                    key=f"lease_sort_{col}"
                )
                
                if sort_col != "None":
                    st.session_state.leases_sort = {
                        'column': col,
                        'direction': True if sort_col == "↑" else False
                    }
        
        # Apply filters
        for col, values in st.session_state.leases_filters.items():
            if values:
                df = df[df[col].isin(values)]
        
        # Apply sort
        if st.session_state.leases_sort['column']:
            df = df.sort_values(
                by=st.session_state.leases_sort['column'],
                ascending=st.session_state.leases_sort['direction']
            )
        
        # Convert filtered DataFrame back to rows for display
        rows = df.values.tolist()

    if rows:
        # Pagination for existing leases
        page = st.session_state.get("existing_page", 1)
        page_size = 5
        total_pages = max(1, (len(rows) + page_size - 1) // page_size)
        if page > total_pages:
            page = total_pages
            st.session_state["existing_page"] = page

        start = (page - 1) * page_size
        end = start + page_size
        page_rows = rows[start:end]

        # Paging controls moved below the table to appear after table rows

        # Adjust column widths for all columns
        header_cols = st.columns([0.8, 1, 1, 1, 1, 1.2, 1.4, 1, 0.8, 0.8])
        headers = ["ID(Cloud Link)", "Tenant Username", "Landlord", "Tenant", "Monthly Rent", "Rent Period", "Address", "Last Updated", "Cloud Link", "Delete"]
        for i, h in enumerate(headers):
            with header_cols[i]:
                st.markdown(f"**{h}**")

        st.markdown("---")

        for r in page_rows:
            cols = st.columns([0.8, 1, 1, 1, 1, 1.2, 1.4, 1, 0.8, 0.8])
            for i, v in enumerate(r):
                with cols[i]:
                    # If this is the ID column and a cloud link exists for this lease, render as clickable link
                    if i == 0:
                        cloud = leases_cloud_map.get(v)
                        if cloud:
                            st.markdown(f'<a href="{cloud}" target="_blank">{v}</a>', unsafe_allow_html=True)
                        else:
                            st.text(v)
                    else:
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

        # Paging controls (below the table)
        ecol1, ecol2, ecol3 = st.columns([1, 1, 1])
        with ecol1:
            if st.button("◀ Prev", key="leases_prev") and page > 1:
                st.session_state["existing_page"] = page - 1
                st.rerun()
        with ecol2:
            st.write(f"Page {page} / {total_pages}")
        with ecol3:
            if st.button("Next ▶", key="leases_next") and page < total_pages:
                st.session_state["existing_page"] = page + 1
                st.rerun()

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

elif st.session_state.current_page == "available_listings":
    # ========== 可租房源页面 ==========
    st.markdown("### 🏘️ Available Listings")
    
    # “新增房源”按钮
    if st.button("➕ Add Listing", key="add_listing_btn", use_container_width=True):
        st.session_state.current_page = "add_listing"
        st.rerun()
    
    if "listing_delete_confirm" not in st.session_state:
        st.session_state.listing_delete_confirm = None

    # 初始化筛选 & 排序状态
    if 'listings_filters' not in st.session_state:
        st.session_state.listings_filters = {}
    if 'listings_sort' not in st.session_state:
        st.session_state.listings_sort = {'column': None, 'direction': None}
        
    listings_path = os.path.join("db", "listings.json")
    rows_data = []
    df = pd.DataFrame()  # 初始化空 DataFrame
    
    if os.path.exists(listings_path):
        try:
            with open(listings_path, "r", encoding="utf-8") as f:
                listings = json.load(f)
            
            # 转成 DataFrame，并把租金 / 面积转成数值方便格式化
            for list_id, m in listings.items():
                landlord_name = m.get("landlord", "-")
                landlord_email = m.get("landlord_email", "")
                landlord_display = f'<a href="mailto:{landlord_email}">{landlord_name}</a>' if landlord_email else landlord_name
                
                # 数值字段统一转 float
                try:
                    mr = float(str(m.get("monthly_rent", "0")).replace("$", "").replace(",", ""))
                except Exception:
                    mr = 0.0
                try:
                    area_val = float(str(m.get("area", "0")))
                except Exception:
                    area_val = 0.0
                
                rows_data.append({
                    'ID': list_id,
                    'Landlord': landlord_display,    # 用于展示（含 mailto 链接）
                    'Landlord Name': landlord_name,  # 用于过滤
                    'Monthly Rent': mr,              # 数值
                    'Area(SQM)': area_val,           # 数值
                    'Property Type': m.get("property_type", "-"),
                    'Rooms': m.get("rooms", "-"),
                    'Address': m.get("property_address", "—"),
                    'Last Updated': m.get("last_updated", "?"),
                })
            
            if rows_data:
                df = pd.DataFrame(rows_data)
            else:
                st.info("No available listings found.")
                st.stop()
            
            # ---------- Filters & Sort（4 列过滤 + 排序） ----------
            st.markdown("#### 🔍 Filters & Sort")
            filter_cols = st.columns(4)
            filter_columns = ['ID', 'Landlord Name', 'Property Type', 'Rooms']
            
            for i, col in enumerate(filter_columns):
                with filter_cols[i]:
                    unique_vals = sorted(df[col].astype(str).unique().tolist())
                    selected = st.multiselect(
                        f"Filter {col}",
                        options=unique_vals,
                        default=[],
                        key=f"filter_{col}",
                        placeholder=f"Search {col}..."
                    )
                    st.session_state.listings_filters[col] = selected
                    
                    sort_col = st.radio(
                        f"Sort {col}",
                        ["None", "↑", "↓"],
                        horizontal=True,
                        key=f"sort_{col}"
                    )
                    if sort_col != "None":
                        st.session_state.listings_sort = {
                            'column': col,
                            'direction': True if sort_col == "↑" else False
                        }
            
            # 应用过滤
            df_filtered = df.copy()
            for col, values in st.session_state.listings_filters.items():
                if values:
                    df_filtered = df_filtered[df_filtered[col].astype(str).isin(values)]
            
            # 应用排序
            if st.session_state.listings_sort['column']:
                df_filtered = df_filtered.sort_values(
                    by=st.session_state.listings_sort['column'],
                    ascending=st.session_state.listings_sort['direction']
                )
            
            if df_filtered.empty:
                st.info("No listings match current filters.")
                st.stop()
            
            # ---------- 分页 ----------
            page = st.session_state.get("listings_page", 1)
            page_size = 5
            total = len(df_filtered)
            total_pages = max(1, (total + page_size - 1) // page_size)
            if page > total_pages:
                page = total_pages
                st.session_state["listings_page"] = page
            
            start = (page - 1) * page_size
            end = start + page_size
            page_df = df_filtered.iloc[start:end].reset_index(drop=True)
            
            # ---------- HTML 表格（带 grid & 数字格式） ----------
            st.markdown("#### 📋 Results")
            
            cols_order = ['ID', 'Landlord', 'Monthly Rent', 'Area(SQM)',
                          'Property Type', 'Rooms', 'Address', 'Last Updated']
            
            # 表头
            header_html = (
                '<table style="width:100%;border-collapse:collapse;">'
                '<thead><tr>' +
                ''.join([
                    f'<th style="border:1px solid #ddd;padding:8px;text-align:left;background:#f6f6f6;">{col}</th>'
                    for col in cols_order
                ]) +
                '</tr></thead>'
            )
            
            # 行数据
            html_rows = []
            for _, r in page_df.iterrows():
                row_html = '<tr>'
                for col in cols_order:
                    val = r[col]
                    if col == 'Monthly Rent':
                        cell = f"${val:,.2f}" if isinstance(val, (int, float)) else str(val)
                    elif col == 'Area(SQM)':
                        cell = f"{val:.1f}" if isinstance(val, (int, float)) else str(val)
                    else:
                        cell = str(val)
                    row_html += f'<td style="border:1px solid #ddd;padding:8px;vertical-align:top;">{cell}</td>'
                row_html += '</tr>'
                html_rows.append(row_html)
            
            table_html = header_html + '<tbody>' + ''.join(html_rows) + '</tbody></table>'
            st.markdown(table_html, unsafe_allow_html=True)
            
            # ---------- 分页按钮 ----------
            lcol1, lcol2, lcol3 = st.columns([1, 1, 1])
            with lcol1:
                if st.button("◀ Prev", key="list_prev") and page > 1:
                    st.session_state["listings_page"] = page - 1
                    st.rerun()
            with lcol2:
                st.write(f"Page {page} / {total_pages} — {total} results")
            with lcol3:
                if st.button("Next ▶", key="list_next") and page < total_pages:
                    st.session_state["listings_page"] = page + 1
                    st.rerun()
            
            # ---------- 删除逻辑：在当前页中选择要删的 ID ----------
            st.markdown("#### 🗑️ Delete Listing")
            delete_options = ["--"] + page_df['ID'].tolist()
            selected_to_delete = st.selectbox(
                "Select a listing ID to delete (current page only)",
                options=delete_options,
                key="list_delete_select"
            )
            
            if st.button("Delete selected listing", key="trigger_del_listing"):
                if selected_to_delete != "--":
                    st.session_state.listing_delete_confirm = selected_to_delete
                else:
                    st.warning("Please select a listing ID first.")
            
            # 二次确认
            if st.session_state.listing_delete_confirm:
                lid = st.session_state.listing_delete_confirm
                st.warning(f"⚠️ Are you sure you want to delete listing {lid}? This action cannot be undone!")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ Confirm Delete", key="confirm_del_listing"):
                        try:
                            if os.path.exists(listings_path):
                                with open(listings_path, "r", encoding="utf-8") as f:
                                    listings = json.load(f)
                                if lid in listings:
                                    del listings[lid]
                                    with open(listings_path, "w", encoding="utf-8") as f:
                                        json.dump(listings, f, ensure_ascii=False, indent=2)
                                    st.success(f"✅ Deleted listing: {lid}")
                                    st.session_state.listing_delete_confirm = None
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"Listing {lid} not found")
                        except Exception as e:
                            st.error(f"❌ Failed to delete listing: {str(e)}")
                with c2:
                    if st.button("❌ Cancel", key="cancel_del_listing"):
                        st.session_state.listing_delete_confirm = None
                        st.rerun()
        
        except json.JSONDecodeError:
            st.warning("⚠️ Corrupted listings.json file")
    else:
        # 如果还没有 listings.json
        st.info("No available listings found. Add a new listing to create the listings database.")



elif st.session_state.current_page == "add_listing":
    # ========== 新增房源页面 ==========
    st.markdown("### ➕ Add New Listing")
    list_id = st.text_input("ID (Unique)", placeholder="e.g. A0001")
    landlord = st.text_input("Landlord", placeholder="e.g. Donald Trump")
    landlord_email = st.text_input("Landlord Email", placeholder="e.g. 123456789@gmail.com")
    monthly_rent = st.text_input("Monthly Rent", placeholder="e.g. 3000")
    area = st.text_input("Area(SQM)", placeholder="e.g. 50")
    property_type = st.selectbox("Property Type", ["Condo", "HDB"]) 
    rooms = st.text_input("Rooms", placeholder="e.g. 2")
    address = st.text_input("Address", placeholder="e.g. 119077")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Add", key="add_listing_confirm"):
            if not list_id:
                st.error("Please provide an ID for the listing.")
            else:
                listings_path = os.path.join("db", "listings.json")
                
                # Load existing listings or create new dictionary
                listings = {}
                if os.path.exists(listings_path):
                    try:
                        with open(listings_path, "r", encoding="utf-8") as f:
                            listings = json.load(f)
                    except json.JSONDecodeError:
                        pass
                
                if list_id in listings:
                    st.error("A listing with this ID already exists.")
                else:
                    try:
                        listings[list_id] = {
                            "landlord": landlord,
                            "landlord_email": landlord_email,
                            "monthly_rent": monthly_rent,
                            "area": area,
                            "property_type": property_type,
                            "rooms": rooms,
                            "property_address": address,
                            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                        # Save all listings back to file
                        os.makedirs("db", exist_ok=True)
                        with open(listings_path, "w", encoding="utf-8") as f:
                            json.dump(listings, f, ensure_ascii=False, indent=2)
                        st.success(f"✅ Added listing {list_id}")
                        st.session_state.current_page = "available_listings"
                        st.session_state.listings_page = 1
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to add listing: {str(e)}")
    with col2:
        if st.button("Return", key="add_listing_return"):
            st.session_state.current_page = "available_listings"
            st.rerun()