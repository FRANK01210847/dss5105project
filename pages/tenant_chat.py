import os
import json
import hashlib
import base64
import streamlit as st
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

def rebuild_pipeline_from_loaded_contracts():
    """根据当前合同重新构建 RAG + Agent"""
    vs_values = list(st.session_state.vectorstores_map.values())
    if not vs_values:
        st.session_state.conversation_chain = None
        st.session_state.chain_invoke_safe = None
        st.session_state.agent = None
        return
    try:
        first_vs = vs_values[0]
        chain, llm, memory, chain_invoke_safe = create_conversation_chain(
            first_vs, openai_api_key=os.getenv("OPENAI_API_KEY")
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
    "tenant_last_contract_id": None
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
with col_left:
    st.markdown("### 📂 Contract Management")

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
# 右侧：聊天问答
# ======================================================================
with col_right:
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
            prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a helpful English-speaking rental assistant."),
                ("human", "{q}\n\nContract context:\n{ctx}")
            ])
            reply = LLMChain(llm=llm, prompt=prompt).run({"q": q, "ctx": contract_info})

            thinking.empty()
            st.markdown(reply)
            scroll_to_bottom()

        st.session_state.chat.append(("assistant", reply))
        st.rerun()
