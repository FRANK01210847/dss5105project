import os
import json
import hashlib
import streamlit as st
from streamlit.components.v1 import html as st_html
from dotenv import load_dotenv

# 🧠 核心 LangChain 结构
from langchain.agents import initialize_agent, AgentType

from langchain_community.chat_models import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
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

# ============== 初始化配置 ==============
load_dotenv()
st.set_page_config(page_title="租客助手 | Smart Rental", page_icon="💬", layout="wide")

# 🚫 完全禁用侧边导航栏
st.markdown("""
    <style>
    /* 隐藏整个侧边导航容器 */
    [data-testid="stSidebarNav"], 
    [data-testid="stSidebarNavLink"],
    [data-testid="stSidebarNavSection"],
    [data-testid="stSidebarHeader"] {
        display: none !important;
        visibility: hidden !important;
    }

    /* 调整侧边栏宽度，只保留自定义的用户信息 */
    [data-testid="stSidebar"] {
        width: 220px !important;
    }
    </style>
""", unsafe_allow_html=True)

# ============== 登录校验 ==============
if st.session_state.get("user_role") != "tenants":
    st.warning("请先以【租客】身份登录。")
    st.switch_page("app.py")

# ============== 侧边栏：用户信息与配置 ==============
with st.sidebar:
    username = st.session_state.get("username", "未知用户")
    st.markdown(f"👋 **当前用户：{username}**")

    # 登出按钮
    if st.button("🚪 退出登录", use_container_width=True):
        st.session_state.clear()
        st.switch_page("app.py")

    st.markdown("---")

    # API Key 状态
    api_key = os.getenv("OPENAI_API_KEY") or st.session_state.get("openai_key")
    if api_key:
        st.success("✅ 已检测到 OpenAI API Key")
    else:
        key_input = st.text_input("🔑 请输入 OpenAI API Key", type="password")
        if key_input:
            os.environ["OPENAI_API_KEY"] = key_input
            st.session_state["openai_key"] = key_input
            st.success("✅ API Key 已保存")

    st.markdown("---")

# ============== 工具函数 ==============
def _file_sha1(uploaded_file) -> str:
    data = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
    return hashlib.sha1(data).hexdigest()

def rebuild_pipeline_from_loaded_contracts():
    """基于当前加载的合同重建 RAG + Agent"""
    vs_values = list(st.session_state.vectorstores_map.values())
    if not vs_values:
        st.session_state.conversation_chain = None
        st.session_state.chain_invoke_safe = None
        st.session_state.agent = None
        return

    base = vs_values[0]
    for other in vs_values[1:]:
        try:
            base.merge_from(other)
        except Exception as e:
            msg = str(e)
            if "already exist" in msg:
                try:
                    base_ids = set(getattr(base.docstore, "_dict", {}).keys())
                    other_store = getattr(other, "docstore", None)
                    other_ids = list(getattr(other_store, "_dict", {}).keys()) if other_store else []
                    new_ids = [i for i in other_ids if i not in base_ids]
                    if new_ids:
                        new_docs = [other_store._dict[i] for i in new_ids]
                        base.add_documents(new_docs)
                except Exception:
                    st.info("检测到重复合同或片段，已跳过重复内容。")
            else:
                raise

    merged_vs = base
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
    )
    st.session_state.conversation_chain = chain
    st.session_state.chain_invoke_safe = chain_invoke_safe
    st.session_state.agent = agent

def scroll_to_bottom():
    st_html(
        """
        <script>
            var chatDiv = window.parent.document.querySelector('.main');
            if (chatDiv) { chatDiv.scrollTop = chatDiv.scrollHeight; }
        </script>
        """,
        height=0
    )

# ============== 初始化状态 ==============
defaults = {
    "chat": [],
    "vectorstores_map": {},
    "loaded_keys": set(),
    "conversation_chain": None,
    "chain_invoke_safe": None,
    "agent": None,
    "current_contract_link": None,  # 当前合同的云端链接
    "current_contract_qr": None,    # 当前合同的二维码路径
    "current_contract_id": None     # 当前合同的ID
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# 顶部品牌
st.markdown("""
<div style="background:#2E8B57;padding:12px 16px;border-radius:12px;margin-bottom:16px;">
  <h3 style="color:#fff;margin:0;">💬 租客智能助手</h3>
</div>
""", unsafe_allow_html=True)

# ============== 左右布局 ==============
col_left, col_right = st.columns([1.15, 2], gap="large")

# ---------------- 左侧：合同管理 ----------------
with col_left:
    st.markdown("### 📂 合同管理")
    

    contract_id = st.text_input("输入租约编号（如 MSH2025-001）")
    if st.button("📥 加载数据库合同", use_container_width=True):
        cid = contract_id.strip()
        if not cid:
            st.info("⚠️ 请先输入合同编号再加载。")
        else:
            db_path = os.path.join("db", cid)
            if not os.path.isdir(db_path):
                st.error("❌ 未找到该租约编号。")
            else:
                # 检查新合同的云端链接信息
                meta_path = os.path.join(db_path, "metadata.json")
                if os.path.exists(meta_path):
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        # 如果新合同有云端链接，更新快速访问
                        if meta.get("cloud_link"):
                            st.session_state.current_contract_link = meta["cloud_link"]
                            st.session_state.current_contract_id = cid
                            if meta.get("qr_code"):
                                qr_path = os.path.join(db_path, meta["qr_code"])
                                if os.path.exists(qr_path):
                                    st.session_state.current_contract_qr = qr_path
                            st.success("✅ 已更新快速访问链接")
                        else:
                            # 如果新合同没有云端链接，清除快速访问
                            st.session_state.current_contract_link = None
                            st.session_state.current_contract_id = None
                            st.session_state.current_contract_qr = None
                            if "current_contract_link" in st.session_state and st.session_state.current_contract_link:
                                st.info("ℹ️ 新合同无云端链接，已清除快速访问")
                
                key = f"db:{cid}"
                if key in st.session_state.loaded_keys:
                    st.info("已加载该合同，自动跳过重复。")
                else:
                    with st.spinner("正在加载合同..."):
                        try:
                            vs = load_vectorstore(db_path, os.getenv("OPENAI_API_KEY"))
                            st.session_state.vectorstores_map[key] = vs
                            st.session_state.loaded_keys.add(key)
                            rebuild_pipeline_from_loaded_contracts()
                            st.success(f"✅ 已加载数据库合同：{cid}")
                        except Exception as e:
                            st.error(f"❌ 加载失败：{e}")

    # 显示当前加载合同的云端链接和二维码
    if st.session_state.current_contract_link:
        st.markdown("---")
        st.markdown("### 📱 当前合同快速访问")
        st.info(f"**当前合同：** {st.session_state.current_contract_id}")
        cols = st.columns([2, 1])
        with cols[0]:
            st.markdown(f"**云端链接：**\n{st.session_state.current_contract_link}")
        if st.session_state.current_contract_qr:
            with cols[1]:
                st.image(st.session_state.current_contract_qr, caption="扫码访问")


    st.markdown("---")
    st.subheader("📎 上传我的合同 PDF")
    up = st.file_uploader("选择 PDF 文件", type=["pdf"])
    if up and st.button("📄 解析 PDF 合同", use_container_width=True):
        sha1 = _file_sha1(up)
        up_key = f"upload:{sha1}:{getattr(up, 'size', 0)}"
        if up_key in st.session_state.loaded_keys:
            st.info("该 PDF 已加载，自动跳过重复。")
        else:
            with st.spinner("正在解析并构建索引..."):
                try:
                    vs = build_vectorstore_from_pdf(up, openai_api_key=os.getenv("OPENAI_API_KEY"))
                    st.session_state.vectorstores_map[up_key] = vs
                    st.session_state.loaded_keys.add(up_key)
                    rebuild_pipeline_from_loaded_contracts()
                    st.success(f"✅ 已加载自定义合同：{up.name}")
                except Exception as e:
                    st.error(f"❌ 解析失败：{e}")

   # ---------------- 当前已加载合同显示 ----------------
    st.markdown("### 📄 当前已加载合同")

    if st.session_state.vectorstores_map:
        delete_keys = []  # 记录要删除的键

        for key in list(st.session_state.vectorstores_map.keys()):
            # 判断来源与显示名
            if key.startswith("db:"):
                source = "📁 数据库"
                name = key.replace("db:", "")
            elif key.startswith("upload:"):
                source = "📎 上传文件"
                name = f"{key.split(':')[1][:8]}..."  # 用 SHA1 的前几位代替
            else:
                source = "❓ 其他"
                name = key

            # 每一行显示
            cols = st.columns([2, 3, 1])
            with cols[0]:
                st.markdown(f"**{source}**")
            with cols[1]:
                st.markdown(name)
            with cols[2]:
                if st.button("❌", key=f"del_{key}", use_container_width=True):
                    delete_keys.append(key)

        # 执行删除操作
        if delete_keys:
            for k in delete_keys:
                if k in st.session_state.vectorstores_map:
                    del st.session_state.vectorstores_map[k]
                st.session_state.loaded_keys.discard(k)
            rebuild_pipeline_from_loaded_contracts()
            st.rerun()

        st.success(f"✅ 当前合同总数：{len(st.session_state.vectorstores_map)}")
    else:
        st.info("📭 暂无已加载合同。可从数据库加载或上传 PDF 文件。")


# ---------------- 右侧：智能问答 ----------------
with col_right:
    # 标题 + 清空按钮
    col1, col2 = st.columns([6, 1])
    with col1:
        st.markdown("### 💬 智能问答")
    with col2:
        if st.button("🗑️", help="清空聊天记录"):
            st.session_state.chat = []
            st.rerun()

    # 聊天内容容器
    chat_container = st.container()
    with chat_container:
        for role, text in st.session_state.chat:
            with st.chat_message("user" if role == "user" else "assistant"):
                st.markdown(text)
    scroll_to_bottom()

    # 固定输入框
    st.markdown(
        """
        <style>
            .stChatInputContainer {
                position: fixed !important;
                bottom: 1rem !important;
                width: 58% !important;
                right: 1rem !important;
                z-index: 999;
                background: white;
                padding-top: 0.5rem;
                border-top: 1px solid #ddd;
            }
        </style>
        """,
        unsafe_allow_html=True
    )

    q = st.chat_input("请输入问题（如：外交条款是什么？可以直接问，不必先加载合同）")

    if q:
        st.session_state.chat.append(("user", q))
        with st.chat_message("user"):
            st.markdown(q)
        scroll_to_bottom()

        with st.chat_message("assistant"):
            thinking = st.empty()
            thinking.markdown("🤔 思考中...")

            reply = ""
            contract_info = ""

            # 1️⃣ 尝试 RAG
            if st.session_state.chain_invoke_safe:
                try:
                    res = st.session_state.chain_invoke_safe({"question": q})
                    contract_info = res.get("answer", "")
                except Exception:
                    pass

            # 2️⃣ 判断是否调用工具
            intent = "NO"
            try:
                intent_llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"))
                prompt = ChatPromptTemplate.from_messages([
                    ("system", "判断用户是否需要计算租金、退租时间或维修责任。若需要，请回答 YES，否则回答 NO。"),
                    ("human", "{q}")
                ])
                ic_chain = LLMChain(llm=intent_llm, prompt=prompt)
                intent = ic_chain.run({"q": q}).strip().upper()
            except Exception:
                pass

            # 3️⃣ 调用 Agent（若需要工具）
            if intent == "YES" and st.session_state.agent:
                try:
                    fused = (
                        f"请根据以下合同信息，先提取相关数据再回答问题：\n\n"
                        f"【合同内容】\n{contract_info}\n\n"
                        f"【用户问题】{q}\n\n"
                        f"如果需要计算，请自动从合同中推断租金、租期等信息并调用合适的工具。"
                    )
                    result = st.session_state.agent.invoke({"input": fused})
                    reply = (
                        result.get("output")
                        or result.get("answer")
                        or result.get("result")
                        or str(result)
                    )
                    reply = reply.split("Observation:")[-1].strip()
                except Exception:
                    reply = ""


            # 4️⃣ 无 Agent → 普通 LLM
            if not reply:
                try:
                    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.2, openai_api_key=os.getenv("OPENAI_API_KEY"))
                    prompt = ChatPromptTemplate.from_messages([
                        ("system", "你是租房助手，请直接给出最终答案，不展示思考过程。"),
                        ("human", f"{q}\n\n（合同上下文，如有）：{contract_info}")
                    ])
                    ans_chain = LLMChain(llm=llm, prompt=prompt)
                    reply = ans_chain.run({"q": q})
                except Exception:
                    reply = "抱歉，暂时无法回答。"

            thinking.empty()
            st.markdown(reply)
            scroll_to_bottom()

        st.session_state.chat.append(("assistant", reply))
        st.rerun()
