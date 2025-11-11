import os
import json
import hashlib
import base64
import streamlit as st
import pandas as pd
from streamlit.components.v1 import html as st_html
from dotenv import load_dotenv

from langchain.agents import initialize_agent, AgentType
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.chains import LLMChain

from utils.rag_utils import (
    load_vectorstore,
    create_conversation_chain,
    build_vectorstore_from_pdf,
)
from utils.rent_tools import (
    calculate_rent,
    calculate_moveout_date,
    get_repair_responsibility,
)

# ================== 初始化配置 ==================
load_dotenv()
st.set_page_config(page_title="Tenant Chat | Smart Rental", page_icon="💬", layout="wide")

st.markdown("""
    <style>
    [data-testid="stSidebarNav"], [data-testid="stSidebarHeader"] {display:none!important;}
    [data-testid="stSidebar"] {width:220px!important;}
    </style>
""", unsafe_allow_html=True)

# ================== 登录验证 ==================
if st.session_state.get("user_role") != "tenants":
    st.warning("Please log in as a tenant to access this page.")
    st.switch_page("app.py")

# ================== 侧边栏 ==================
with st.sidebar:
    username = st.session_state.get("username", "Unknown User")
    st.markdown(f"👋 **Current User: {username}**")

    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.clear()
        st.switch_page("app.py")

    st.markdown("---")
    
    # Add navigation buttons
    if "current_view" not in st.session_state:
        st.session_state.current_view = "chat"
    
    if st.button("💬 Chat Assistant", 
                 key="nav_chat",
                 type="primary" if st.session_state.current_view == "chat" else "secondary",
                 use_container_width=True):
        if st.session_state.current_view != "chat":
            # Clear all states
            st.session_state.chat = []
            st.session_state.vectorstores_map = {}
            st.session_state.loaded_keys = set()
            st.session_state.contract_meta_map = {}
            st.session_state.contract_summary = None
            st.session_state.contract_load_success = None
            st.session_state.contract_payment_info = None
        st.session_state.current_view = "chat"
        st.rerun()
    
    if st.button("🏘️ Browse Listings", 
                 key="nav_listings",
                 type="primary" if st.session_state.current_view == "listings" else "secondary",
                 use_container_width=True):
        if st.session_state.current_view != "listings":
            # Clear all states
            st.session_state.chat = []
            st.session_state.vectorstores_map = {}
            st.session_state.loaded_keys = set()
            st.session_state.contract_meta_map = {}
            st.session_state.contract_summary = None
            st.session_state.contract_load_success = None
            st.session_state.contract_payment_info = None
        st.session_state.current_view = "listings"
        st.rerun()

    if st.button("📄 My Contract",
                 key="nav_my_contract",
                 type="primary" if st.session_state.current_view == "my_contract" else "secondary",
                 use_container_width=True):
        if st.session_state.current_view != "my_contract":
            # Clear states but keep contract info if coming back to My Contract
            st.session_state.chat = []
            st.session_state.vectorstores_map = {}
            st.session_state.loaded_keys = set()
            st.session_state.contract_meta_map = {}
            # Only reset contract display info if not already in my_contract view
            if st.session_state.current_view not in ("my_contract", None):
                st.session_state.contract_summary = None
                st.session_state.contract_load_success = None
                st.session_state.contract_payment_info = None
                st.session_state.should_load_my_contract = True
        st.session_state.current_view = "my_contract"
        st.rerun()

    st.markdown("---")
    api_key = os.getenv("OPENAI_API_KEY") or st.session_state.get("openai_key")
    if api_key:
        st.success("✅ Detected OpenAI API Key")
    else:
        key_input = st.text_input("🔑 Enter OpenAI API Key", type="password")
        if key_input:
            os.environ["OPENAI_API_KEY"] = key_input
            st.session_state["openai_key"] = key_input
            st.success("✅ API Key saved")

# ================== 工具函数 ==================
def _file_sha1(uploaded_file):
    data = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
    return hashlib.sha1(data).hexdigest()

def scroll_to_bottom():
    st_html("<script>window.scrollTo(0, document.body.scrollHeight);</script>", height=0)

def extract_contract_info(contract_id, vectorstore=None):
    """Extract contract information from metadata.json or vectorstore"""
    from datetime import datetime, timedelta
    import calendar
    import re

    info = {
        'monthly_rent': None,
        'lease_term': None,
        'address': None,
        'landlord_name': None,
        'landlord_contact': None,
        'rent_due_day': None,  # Day of month rent is due
        'next_payment_date': None,
        'days_until_payment': None
    }
    
    # Try metadata.json first
    meta_path = os.path.join("db", contract_id, "metadata.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                info['monthly_rent'] = meta.get('monthly_rent')
                info['lease_term'] = meta.get('lease_term')
                info['address'] = meta.get('property_address')
                info['landlord_name'] = meta.get('landlord')
                info['landlord_contact'] = meta.get('landlord_contact')
        except Exception:
            pass

    # If vectorstore provided and some info missing, try to extract from contract text
    if vectorstore and (not all([info['monthly_rent'], info['lease_term'], info['landlord_name']])):
        try:
            llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"))
            questions = [
                "What is the monthly rent amount in this contract?",
                "What is the lease term or duration in this contract?",
                "What is the landlord's name and contact information in this contract?",
                "On what day of each month is the rent payment due?"
            ]
            
            for q in questions:
                try:
                    docs = vectorstore.similarity_search(q, k=3)
                    context = "\n".join(d.page_content for d in docs)
                    
                    prompt = f"""Based on this contract excerpt, answer the question below.
                    If you can't find the exact information, say "not found".
                    Extract only the specific information asked for, don't explain.
                    
                    Contract text:
                    {context}
                    
                    Question: {q}
                    """
                    
                    response = llm.predict(prompt).strip()
                    
                    if "not found" not in response.lower():
                        if "monthly rent" in q.lower():
                            # Try to extract dollar amount
                            amount = re.search(r'\$?(\d+(?:,\d{3})*(?:\.\d{2})?)', response)
                            if amount:
                                info['monthly_rent'] = amount.group(0)
                        elif "lease term" in q.lower():
                            info['lease_term'] = response
                        elif "landlord" in q.lower():
                            info['landlord_name'] = response.split(",")[0] if "," in response else response
                            info['landlord_contact'] = response.split(",")[1].strip() if "," in response else None
                        elif "rent payment due" in q.lower():
                            # Try to extract day of month
                            day_match = re.search(r'(\d+)(?:st|nd|rd|th)?(?:\s+(?:day|of))?', response.lower())
                            if day_match:
                                info['rent_due_day'] = int(day_match.group(1))
                except Exception:
                    continue
        except Exception as e:
            st.warning(f"Could not extract some information from contract: {str(e)}")

    # Calculate next payment date and days until payment
    try:
        # Use extracted due day or default to last day of month
        due_day = info['rent_due_day'] or calendar.monthrange(datetime.now().year, datetime.now().month)[1]
        
        # Calculate next payment date
        today = datetime.now()
        this_month_payment = today.replace(day=due_day)
        
        # If today is past the due day, next payment is next month
        if today > this_month_payment:
            if today.month == 12:
                next_payment = this_month_payment.replace(year=today.year + 1, month=1)
            else:
                next_payment = this_month_payment.replace(month=today.month + 1)
        else:
            next_payment = this_month_payment
        
        info['next_payment_date'] = next_payment.strftime("%Y-%m-%d")
        info['days_until_payment'] = (next_payment - today).days

    except Exception:
        pass

    return info

def rebuild_pipeline_from_loaded_contracts():
    """根据当前已加载的所有合同，重新构建 RAG + Agent（支持多份合同）"""
    vs_values = list(st.session_state.vectorstores_map.values())
    if not vs_values:
        st.session_state.conversation_chain = None
        st.session_state.chain_invoke_safe = None
        st.session_state.agent = None
        return

    try:
        # ⭐ 合并所有合同的向量库
        # 以第一个为基底，把后面的都 merge 进来
        merged_vs = vs_values[0]
        for other_vs in vs_values[1:]:
            # 有的 langchain 版本叫 merge_from，有的叫 merge_from
            # 通常 FAISS 都有 merge_from 方法
            merged_vs.merge_from(other_vs)

        # 用“合并后的向量库”来构建对话链
        chain, llm, memory, chain_invoke_safe = create_conversation_chain(
            merged_vs, openai_api_key=os.getenv("OPENAI_API_KEY")
        )

        tools = [calculate_rent, calculate_moveout_date, get_repair_responsibility]
        agent = initialize_agent(
            tools=tools,
            llm=llm,
            agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
            verbose=False,
            memory=memory,
            handle_parsing_errors=True,
        )

        st.session_state.conversation_chain = chain
        st.session_state.chain_invoke_safe = chain_invoke_safe
        st.session_state.agent = agent

    except Exception as e:
        st.error(f"❌ Pipeline rebuild failed: {e}")


# ================== 初始化 session 状态 ==================
defaults = {
    "chat": [],
    "vectorstores_map": {},
    "loaded_keys": set(),
    "contract_meta_map": {},
    "conversation_chain": None,
    "chain_invoke_safe": None,
    "agent": None,
    "tenant_last_qr": None,
    "tenant_last_contract_id": None,
    "contract_summary": None,
    "contract_load_success": None,
    "contract_payment_info": None
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ================== 页面标题 ==================
st.markdown("""
<div style="background:#2E8B57;padding:12px 16px;border-radius:12px;margin-bottom:16px;">
  <h3 style="color:#fff;margin:0;">💬 Tenant Smart Assistant</h3>
</div>
""", unsafe_allow_html=True)

col_left, col_right = st.columns([1.1, 2], gap="large")

# ======================================================================
# 左侧：合同管理
# ======================================================================
if st.session_state.current_view in ("chat", "my_contract"):
    with col_left:
        # === 加载合同 ===
        if st.session_state.current_view == "chat":
            st.markdown("### 📂 Contract Management")
        else:
            st.markdown("### 📂 My Contract")
        # Two modes: normal chat (user enters Lease ID), or my_contract (auto-load based on db/contracts.json)
        if st.session_state.current_view == "chat":
            contract_id = st.text_input("Enter Lease ID (e.g., 2025002)")
            if st.button("📥 Load Database Contract", use_container_width=True):
                cid = contract_id.strip()
                if not cid:
                    st.info("⚠️ Please enter a lease ID before loading.")
                else:
                    db_path = os.path.join("db", cid)
                    if not os.path.isdir(db_path):
                        st.error("❌ Lease ID not found.")
                    else:
                        key = f"db:{cid}"
                        if key in st.session_state.loaded_keys:
                            st.info("Contract already loaded.")
                        else:
                            with st.spinner("Loading contract..."):
                                try:
                                    vs = load_vectorstore(db_path, os.getenv("OPENAI_API_KEY"))
                                    st.session_state.vectorstores_map[key] = vs
                                    st.session_state.loaded_keys.add(key)

                                    meta = {"contract_id": cid}
                                    meta_path = os.path.join(db_path, "metadata.json")
                                    if os.path.exists(meta_path):
                                        with open(meta_path, "r", encoding="utf-8") as f:
                                            meta.update(json.load(f))
                                    st.session_state.contract_meta_map[key] = meta
                                    rebuild_pipeline_from_loaded_contracts()
                                    st.success(f"✅ Database contract loaded: {cid}")
                                except Exception as e:
                                    st.error(f"❌ Loading failed: {e}")
        else:
            # My Contract mode: look up db/contracts.json for this tenant's username and auto-load
            username = st.session_state.get("username")
            st.markdown(f"**My Username:** {username}")
            contracts_path = os.path.join("db", "contracts.json")
            tenant_props = None
            if os.path.exists(contracts_path):
                try:
                    with open(contracts_path, "r", encoding="utf-8") as cf:
                        contracts = json.load(cf)
                    tenant_props = contracts.get(username)
                except Exception:
                    tenant_props = None

            if not tenant_props:
                st.info("No contract found for your username.")
            else:
                # normalize to list
                if isinstance(tenant_props, str):
                    tenant_props = [tenant_props]

                chosen_cid = tenant_props[0] if len(tenant_props) == 1 else st.selectbox("Select your contract (if multiple)", options=tenant_props)

                # Try to load contract if needed
                vs = None
                db_path = os.path.join("db", chosen_cid)
                key = f"db:{chosen_cid}"

                # Always try to load contract first
                if not os.path.isdir(db_path):
                    st.error("❌ Lease ID not found in db.")
                elif key not in st.session_state.loaded_keys:
                    with st.spinner("Loading your contract..."):
                        try:
                            vs = load_vectorstore(db_path, os.getenv("OPENAI_API_KEY"))
                            st.session_state.vectorstores_map[key] = vs
                            st.session_state.loaded_keys.add(key)

                            meta = {"contract_id": chosen_cid}
                            meta_path = os.path.join(db_path, "metadata.json")
                            if os.path.exists(meta_path):
                                with open(meta_path, "r", encoding="utf-8") as f:
                                    meta.update(json.load(f))
                            st.session_state.contract_meta_map[key] = meta
                            rebuild_pipeline_from_loaded_contracts()
                            
                            # Extract contract information
                            info = extract_contract_info(chosen_cid, vs)
                            
                            # Format amount with dollar sign if not present
                            rent = info.get('monthly_rent')
                            if rent and not str(rent).startswith('$'):
                                rent = f"${rent}"
                            
                            # Save contract info to session state
                            st.session_state.contract_summary = {
                                'rent': rent,
                                'lease_term': info.get('lease_term'),
                                'address': info.get('address'),
                                'landlord_name': info.get('landlord_name'),
                                'landlord_contact': info.get('landlord_contact')
                            }
                            
                            if info.get('next_payment_date') and info.get('days_until_payment') is not None:
                                st.session_state.contract_payment_info = {
                                    'next_date': info['next_payment_date'],
                                    'days_remaining': info['days_until_payment']
                                }
                            st.session_state.contract_load_success = chosen_cid
                        except Exception as e:
                            st.error(f"❌ Loading failed: {e}")

                # After loading (or if already loaded), show the summary
                if st.session_state.contract_load_success:
                    st.success(f"✅ Database contract loaded: {st.session_state.contract_load_success}")

                # Show contract summary if available
                if st.session_state.contract_summary:
                    st.markdown("### 📋 Contract Summary")
                    summary = st.session_state.contract_summary
                    st.markdown(f"""
                    **Monthly Rent:** {summary['rent'] or '—'}  
                    **Lease Term:** {summary['lease_term'] or '—'}  
                    **Property Address:** {summary['address'] or '—'}  
                    **Landlord:** {summary['landlord_name'] or '—'}  
                    **Landlord Contact:** {summary['landlord_contact'] or '—'}
                    """)
                
                if st.session_state.contract_payment_info:
                    payment = st.session_state.contract_payment_info
                    days = payment['days_remaining']
                    if days <= 7:
                        st.warning(f"⚠️ **Rent Payment Reminder:** Next payment due in {days} days on {payment['next_date']}")
                    else:
                        st.info(f"💰 **Next Rent Payment:** Due on {payment['next_date']} ({days} days from now)")
                should_load = st.session_state.get("should_load_my_contract", True)
                if should_load and not os.path.isdir(db_path):
                    st.error("❌ Lease ID not found in db.")
                elif should_load and key not in st.session_state.loaded_keys:
                    with st.spinner("Loading your contract..."):
                        try:
                            vs = load_vectorstore(db_path, os.getenv("OPENAI_API_KEY"))
                            st.session_state.vectorstores_map[key] = vs
                            st.session_state.loaded_keys.add(key)

                            meta = {"contract_id": chosen_cid}
                            meta_path = os.path.join(db_path, "metadata.json")
                            if os.path.exists(meta_path):
                                with open(meta_path, "r", encoding="utf-8") as f:
                                    meta.update(json.load(f))
                            st.session_state.contract_meta_map[key] = meta
                            rebuild_pipeline_from_loaded_contracts()
                            
                            # Extract contract information
                            info = extract_contract_info(chosen_cid, vs)
                            
                            # Format amount with dollar sign if not present
                            rent = info.get('monthly_rent')
                            if rent and not str(rent).startswith('$'):
                                rent = f"${rent}"
                            
                            # Save contract info to session state
                            st.session_state.contract_summary = {
                                'rent': rent,
                                'lease_term': info.get('lease_term'),
                                'address': info.get('address'),
                                'landlord_name': info.get('landlord_name'),
                                'landlord_contact': info.get('landlord_contact')
                            }
                            
                            if info.get('next_payment_date') and info.get('days_until_payment') is not None:
                                st.session_state.contract_payment_info = {
                                    'next_date': info['next_payment_date'],
                                    'days_remaining': info['days_until_payment']
                                }
                            
                            st.session_state.contract_load_success = chosen_cid
                            st.session_state.should_load_my_contract = False
                            
                            # Show payment info if available
                            if info.get('next_payment_date') and info.get('days_until_payment') is not None:
                                days_until = info['days_until_payment']
                                if days_until <= 7:
                                    st.warning(f"⚠️ **Rent Payment Reminder:** Next payment due in {days_until} days on {info['next_payment_date']}")
                                else:
                                    st.info(f"💰 **Next Rent Payment:** Due on {info['next_payment_date']} ({days_until} days from now)")
                            
                            st.success(f"✅ Your contract loaded: {chosen_cid}")
                            st.session_state.should_load_my_contract = False
                        except Exception as e:
                            st.error(f"❌ Loading failed: {e}")
                
                
        if st.session_state.current_view == "chat":
            # === 上传临时合同 ===
            st.markdown("---")
            st.subheader("📎 Upload My Contract PDF (Temporary)")
            up = st.file_uploader("Select PDF file", type=["pdf"])
            if up and st.button("📄 Parse Contract", use_container_width=True):
                sha1 = _file_sha1(up)
                up_key = f"upload:{sha1}"
                if up_key in st.session_state.loaded_keys:
                    st.info("This PDF is already loaded.")
                else:
                    with st.spinner("Parsing and building index..."):
                        try:
                            vs = build_vectorstore_from_pdf(up, openai_api_key=os.getenv("OPENAI_API_KEY"))
                            st.session_state.vectorstores_map[up_key] = vs
                            st.session_state.loaded_keys.add(up_key)
                            st.session_state.contract_meta_map[up_key] = {
                                "contract_id": f"Uploaded-{sha1[:6]}",
                                "source": "upload",
                            }
                            rebuild_pipeline_from_loaded_contracts()
                            st.success(f"✅ Contract loaded: {up.name}")
                        except Exception as e:
                            st.error(f"❌ Parsing failed: {e}")

        # === 合同列表 ===
        st.markdown("---")
        st.markdown("### 📄 Loaded Contracts")
        if st.session_state.vectorstores_map:
            delete_keys = []
            for key in list(st.session_state.vectorstores_map.keys()):
                meta = st.session_state.contract_meta_map.get(key, {})
                name = meta.get("property_id") or meta.get("contract_id") or key
                
                # 第一行：基本信息和删除按钮
                cols = st.columns([3, 2, 1])
                with cols[0]:
                    icon = "📁" if key.startswith("db:") else "📎"
                    st.markdown(f"**{icon} {name}**")
                with cols[1]:
                    rent_val = meta.get("monthly_rent")
                    # 如果元数据中没有租金，则尝试自动解析合同文本中的金额
                    if not rent_val:
                        try:
                            contract_path = os.path.join("db", meta.get("contract_id", ""), "contract.pdf")
                            if os.path.exists(contract_path):
                                from langchain_community.document_loaders import PyPDFLoader
                                loader = PyPDFLoader(contract_path)
                                pages = loader.load()
                                text = "\n".join(p.page_content for p in pages)
                                import re
                                match = re.search(r"\$?\s?S?\$?\s?(\d{3,6})", text)
                                if match:
                                    rent_val = f"S${match.group(1)}"
                                    meta["monthly_rent"] = rent_val  # 缓存到 session
                        except Exception:
                            pass
                    st.write(f"Rent: {rent_val}" if rent_val else "Rent: —")
                with cols[2]:
                    if st.button("❌", key=f"del_{key}", help="Remove this contract"):
                        delete_keys.append(key)
                
                # 第二行：Quick Access 下拉栏
                with st.expander("🔗 Contract Easy Access", expanded=False):
                    # 云端链接
                    cloud_link = meta.get("cloud_link")
                    if cloud_link:
                        st.markdown(f"**Cloud Link**: <a href='{cloud_link}' target='_blank'>{cloud_link}</a>", unsafe_allow_html=True)
                    else:
                        st.info("No cloud link available")
                    
                    # 二维码
                    contract_id = meta.get("contract_id")
                    if contract_id:
                        qr_path = os.path.join("db", contract_id, "contract_qr.png")
                        if os.path.exists(qr_path):
                            with open(qr_path, "rb") as f:
                                b64 = base64.b64encode(f.read()).decode()
                                st.markdown(f"**QR Code**:<br><img src='data:image/png;base64,{b64}' width='150'>", unsafe_allow_html=True)
                
                # 分隔线
                st.markdown("---")
            if delete_keys:
                for dk in delete_keys:
                    # 删除当前二维码对应合同时清空显示
                    if st.session_state.get("tenant_last_contract_id") and \
                    st.session_state["tenant_last_contract_id"] in dk:
                        st.session_state["tenant_last_qr"] = None
                        st.session_state["last_contract_display"] = None
                        st.session_state["tenant_last_contract_id"] = None

                    st.session_state.vectorstores_map.pop(dk, None)
                    st.session_state.loaded_keys.discard(dk)
                    st.session_state.contract_meta_map.pop(dk, None)
                rebuild_pipeline_from_loaded_contracts()
                st.rerun()
            st.success(f"✅ Current contract count: {len(st.session_state.vectorstores_map)}")
        else:
            st.info("📭 No contracts loaded yet.")

    # ======================================================================
    # 右侧：根据当前视图显示不同内容
    # ======================================================================
    with col_right:
        # 聊天问答界面
        head_l, head_r = st.columns([6, 1])
        with head_l:
            st.markdown("### 💬 Intelligent Q&A")
        with head_r:
            if st.button("🗑"):
                st.session_state.chat = []
                st.rerun()

        chat_container = st.container()
        with chat_container:
            for role, text in st.session_state.chat:
                with st.chat_message("user" if role == "user" else "assistant"):
                    st.markdown(text)
        scroll_to_bottom()

        q = st.chat_input("Ask a question about your rental contract...")
        if q:
            st.session_state.chat.append(("user", q))
            with st.chat_message("user"):
                st.markdown(q)
            scroll_to_bottom()

            with st.chat_message("assistant"):
                thinking = st.empty()
                thinking.markdown("🤔 Thinking...")

                reply = ""
                contract_info = ""

                if st.session_state.chain_invoke_safe:
                    try:
                        res = st.session_state.chain_invoke_safe({"question": q})
                        contract_info = res.get("answer", "")
                    except Exception:
                        contract_info = ""

                llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.3, openai_api_key=os.getenv("OPENAI_API_KEY"))
                
                # 根据是否有合同加载来选择不同的prompt
                if len(st.session_state.vectorstores_map)>1:
                    prompt = ChatPromptTemplate.from_messages([
                        ("system",
                        "You are a helpful English-speaking rental assistant. "
                        "The user may load one or more rental contracts at the same time. "
                        "When the user asks about 'these two contracts', 'each contract', "
                        "or uses plural form, please answer separately for each relevant contract, "
                        "and clearly indicate which contract you are talking about "
                        "(for example, by address, property ID, or other unique wording in the text)."),
                        ("human", "{q}\n\nContract context (may contain multiple contracts mixed together):\n{ctx}")
                    ])
                elif len(st.session_state.vectorstores_map)==1:
                    prompt = ChatPromptTemplate.from_messages([
                        ("system", "You are a helpful English-speaking rental assistant."),
                        ("human", "{q}\n\nContract context:\n{ctx}")
                    ])
                else:
                    prompt = ChatPromptTemplate.from_messages([
                        ("system",
                        "You are a helpful and knowledgeable English-speaking rental assistant. "
                        "You can provide general advice about renting, tenant rights, rental procedures, "
                        "and answer questions about common rental situations. "
                        "Make your responses informative but concise, and always maintain a friendly and professional tone."),
                        ("human", "{q}")
                    ])

                reply = LLMChain(llm=llm, prompt=prompt).run({"q": q, "ctx": contract_info})

                thinking.empty()
                st.markdown(reply)
                scroll_to_bottom()

            st.session_state.chat.append(("assistant", reply))
            st.rerun()
    
else:  # listings view
    st.markdown("### 🏘️ Available Listings")

    # Load listings data from single JSON
    listings_path = os.path.join("db", "listings.json")
    if not os.path.exists(listings_path):
        st.info("No listings database found")
    else:
        try:
            with open(listings_path, "r", encoding="utf-8") as f:
                listings = json.load(f)

            # Build rows with all required columns
            rows = []
            for list_id, m in listings.items():
                landlord_name = m.get("landlord", "-")
                landlord_email = m.get("landlord_email")
                landlord_display = f'<a href="mailto:{landlord_email}">{landlord_name}</a>' if landlord_email else landlord_name

                # Normalize numeric fields safely
                try:
                    mr = float(str(m.get("monthly_rent", "0")).replace("$", "").replace(",", ""))
                except Exception:
                    mr = 0.0
                try:
                    area = float(str(m.get("area", "0")))
                except Exception:
                    area = 0.0

                rows.append({
                    'ID': list_id,
                    'Landlord': landlord_display,
                    'Landlord Name': landlord_name,
                    'Monthly Rent': mr,
                    'Area(SQM)': area,
                    'Property Type': m.get("property_type", "-"),
                    'Rooms': m.get("rooms", "-"),
                    'Address': m.get("property_address", "—"),
                    'Last Updated': m.get("last_updated", "?")
                })

            if not rows:
                st.info("No available listings found")
            else:
                df = pd.DataFrame(rows)

                # Filters: Monthly Rent slider, Area slider, Property Type, Rooms, Address
                st.markdown("#### 🔍 Filters")

                # Price range slider (fixed 0-10000 per request)
                # clamp defaults to slider bounds
                pr_min = float(df['Monthly Rent'].min())
                pr_max = float(df['Monthly Rent'].max())
                default_pr_min = max(0.0, min(pr_min, 10000.0))
                default_pr_max = max(0.0, min(pr_max, 10000.0))
                price_range = st.slider(
                    "Monthly Rent ($)", 0.0, 10000.0,
                    (default_pr_min, default_pr_max),
                    step=50.0
                )

                # Area range slider (fixed 0-200)
                a_min = float(df['Area(SQM)'].min())
                a_max = float(df['Area(SQM)'].max())
                default_a_min = max(0.0, min(a_min, 200.0))
                default_a_max = max(0.0, min(a_max, 200.0))
                area_range = st.slider(
                    "Area (SQM)", 0.0, 200.0,
                    (default_a_min, default_a_max),
                    step=1.0
                )

                # Property Type and Rooms multi-selects
                c1, c2 = st.columns(2)
                with c1:
                    property_types = sorted(df['Property Type'].fillna("-").unique().tolist())
                    selected_types = st.multiselect("Property Type", options=property_types, default=property_types)
                with c2:
                    rooms = sorted(df['Rooms'].fillna("-").unique().tolist())
                    selected_rooms = st.multiselect("Rooms", options=rooms, default=rooms)

                # District filter (extract first two digits of 6-digit Singapore postal code)
                import re
                def _extract_district(addr):
                    if not addr:
                        return "--"
                    s = str(addr)
                    m = re.search(r"(\d{6})", s)
                    if m:
                        return m.group(1)[:2]
                    # fallback: take first two digits found
                    digits = re.sub(r"\D", "", s)
                    return digits[:2] if len(digits) >= 2 else "--"

                df['District'] = df['Address'].apply(_extract_district)
                districts = sorted(df['District'].unique().tolist())
                selected_districts = st.multiselect("District (first 2 digits of postal code)", options=districts, default=districts)

                # Apply filters
                mask = (
                    df['Monthly Rent'].between(price_range[0], price_range[1]) &
                    df['Area(SQM)'].between(area_range[0], area_range[1]) &
                    df['Property Type'].isin(selected_types) &
                    df['Rooms'].isin(selected_rooms) &
                    df['District'].isin(selected_districts)
                )

                filtered = df[mask].reset_index(drop=True)

                # Pagination: 5 items per page
                if 'tenant_listings_page' not in st.session_state:
                    st.session_state.tenant_listings_page = 1
                page = st.session_state.tenant_listings_page
                page_size = 5
                total = len(filtered)
                total_pages = max(1, (total + page_size - 1) // page_size)
                if page > total_pages:
                    page = total_pages
                    st.session_state.tenant_listings_page = page
                start = (page - 1) * page_size
                end = start + page_size
                page_df = filtered.iloc[start:end]

                # Render as HTML table to allow mailto links in Landlord column (only current page)
                cols_order = ['ID', 'Landlord', 'Monthly Rent', 'Area(SQM)', 'Property Type', 'Rooms', 'Address', 'Last Updated']
                html_rows = []
                header_html = '<table class="tbl" style="width:100%;border-collapse:collapse;"><thead><tr>' + ''.join([f'<th style="border:1px solid #ddd;padding:8px;text-align:left;background:#f6f6f6;">{col}</th>' for col in cols_order]) + '</tr></thead>'

                for _, r in page_df.iterrows():
                    row_html = '<tr>'
                    for col in cols_order:
                        val = r[col]
                        if col == 'Monthly Rent':
                            cell = f"${val:,.2f}" if isinstance(val, (int, float)) else str(val)
                        else:
                            cell = str(val)
                        row_html += f'<td style="border:1px solid #ddd;padding:8px;">{cell}</td>'
                    row_html += '</tr>'
                    html_rows.append(row_html)

                table_html = header_html + '<tbody>' + ''.join(html_rows) + '</tbody></table>'

                st.markdown("#### 📋 Results")
                st.markdown(table_html, unsafe_allow_html=True)

                # Paging controls
                pcol1, pcol2, pcol3 = st.columns([1, 1, 1])
                with pcol1:
                    if st.button("◀ Prev", key="tenant_prev") and page > 1:
                        st.session_state.tenant_listings_page = page - 1
                        st.rerun()
                with pcol2:
                    st.write(f"Page {page} / {total_pages} — {total} results")
                with pcol3:
                    if st.button("Next ▶", key="tenant_next") and page < total_pages:
                        st.session_state.tenant_listings_page = page + 1
                        st.rerun()

        except Exception as e:
            st.error(f"Error loading listings: {str(e)}")

    # 聊天问答界面
    head_l, head_r = st.columns([6, 1])
    with head_l:
        st.markdown("### 💬 Intelligent Q&A")
    with head_r:
        if st.button("🗑"):
            st.session_state.chat = []
            st.rerun()

    chat_container = st.container()
    with chat_container:
        for role, text in st.session_state.chat:
            with st.chat_message("user" if role == "user" else "assistant"):
                st.markdown(text)
    scroll_to_bottom()

    q = st.chat_input("Ask a question...")
    if q:
        st.session_state.chat.append(("user", q))
        with st.chat_message("user"):
            st.markdown(q)
        scroll_to_bottom()

        with st.chat_message("assistant"):
            thinking = st.empty()
            thinking.markdown("🤔 Thinking...")

            reply = ""
            contract_info = ""

            if st.session_state.chain_invoke_safe:
                try:
                    res = st.session_state.chain_invoke_safe({"question": q})
                    contract_info = res.get("answer", "")
                except Exception:
                    contract_info = ""

            llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.3, openai_api_key=os.getenv("OPENAI_API_KEY"))
            
            prompt = ChatPromptTemplate.from_messages([
                ("system",
                "You are a helpful and knowledgeable English-speaking rental assistant. "
                "You can provide general advice about renting, tenant rights, rental procedures, "
                "and answer questions about common rental situations. "
                "Make your responses informative but concise, and always maintain a friendly and professional tone."),
                ("human", "{q}")
            ])


            reply = LLMChain(llm=llm, prompt=prompt).run({"q": q, "ctx": contract_info})

            thinking.empty()
            st.markdown(reply)
            scroll_to_bottom()

        st.session_state.chat.append(("assistant", reply))
        st.rerun()


