#!/usr/bin/env python3
"""
租房助手Chatbot：基于GenAI+LangChain+Streamlit的租户-房东智能助手
支持租房合同Q&A、维修责任查询、退租指引、租金计算等功能
运行命令：streamlit run doubao.py
"""
import streamlit as st
import os
import tempfile
import json
from typing import Optional, List, Dict
from datetime import datetime
import time

# 环境变量与依赖检查
try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

# LangChain核心依赖（RAG、LLM、工具链）
try:
    from langchain_community.document_loaders import PyPDFLoader
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.embeddings import OpenAIEmbeddings
    from langchain_community.vectorstores import FAISS
    from langchain_community.chat_models import ChatOpenAI
    from langchain.chains import ConversationalRetrievalChain, LLMChain
    from langchain.memory import ConversationBufferMemory
    from langchain.prompts import ChatPromptTemplate
    from langchain.tools import tool
    from langchain.agents import initialize_agent, AgentType
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

# 页面配置（优先执行）
st.set_page_config(
    page_title="租房助手Chatbot",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------- 1. 基础配置：CSS与状态初始化 ----------------------
def setup_custom_css():
    st.markdown("""
    <style>
    .main-header {
        font-size: 2.2rem;
        color: #2E8B57;
        text-align: center;
        margin: 1.5rem 0;
        font-weight: bold;
    }
    .chat-container {
        max-height: 600px;
        overflow-y: auto;
        padding: 1rem;
    }
    .chat-message {
        padding: 1.2rem;
        border-radius: 0.8rem;
        margin: 0.8rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .user-message {
        background-color: #F0F8FF;
        border-left: 5px solid #4169E1;
        text-align: right;
    }
    .assistant-message {
        background-color: #F8F8FF;
        border-left: 5px solid #2E8B57;
    }
    .sample-btn {
        background-color: #F5F5F5;
        border: 1px solid #DDD;
        border-radius: 0.5rem;
        padding: 0.8rem;
        margin: 0.5rem 0;
        width: 100%;
        text-align: left;
        transition: all 0.3s;
    }
    .sample-btn:hover {
        background-color: #E8F5E9;
        border-color: #2E8B57;
    }
    .test-note {
        background-color: #E8F5E9;
        color: #2E8B57;
        padding: 0.3rem 0.6rem;
        border-radius: 0.3rem;
        font-size: 0.9rem;
    }
    </style>
    """, unsafe_allow_html=True)

def initialize_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "您好！我是租房助手，可帮您解答合同疑问、维修责任、退租流程等问题。请上传租房合同PDF，或直接提问～"}
        ]
    if "uploaded_file" not in st.session_state:
        st.session_state.uploaded_file = None
    if "uploaded_file_name" not in st.session_state:
        st.session_state.uploaded_file_name = None
    if "pdf_processed" not in st.session_state:
        st.session_state.pdf_processed = False
    if "doc_chunk_count" not in st.session_state:
        st.session_state.doc_chunk_count = 0
    if "is_thinking" not in st.session_state:
        st.session_state.is_thinking = False
    if "new_message" not in st.session_state:
        st.session_state.new_message = False
    # 新增：用于跟踪最后处理的输入
    if "last_processed_input" not in st.session_state:
        st.session_state.last_processed_input = None
    # OpenAI相关状态
    if "vectorstore" not in st.session_state:
        st.session_state.vectorstore = None
    if "conversation_chain" not in st.session_state:
        st.session_state.conversation_chain = None
    if "agent" not in st.session_state:
        st.session_state.agent = None
    if "model_config" not in st.session_state:
        st.session_state.model_config = {
            "temperature": 0.2,
            "max_tokens": 1500,
            "chunk_size": 1000,
            "chunk_overlap": 200
        }

# ---------------------- 2. 工具定义：租金计算、退租日期计算等 ----------------------
@tool(return_direct=True)
def calculate_rent(
    monthly_rent: float, 
    stay_months: int, 
    deposit: float = 0.0, 
    is_early_termination: bool = False,
    notice_period_months: int = 2
) -> str:
    """
    计算租房相关的租金和押金金额，支持提前退租的违约金计算。
    
    参数:
    monthly_rent: 每月租金金额（单位：新元）
    stay_months: 实际居住的月数
    deposit: 已支付的押金（通常为1-2个月租金）
    is_early_termination: 是否提前退租（True/False）
    notice_period_months: 提前退租的通知期（默认2个月）
    
    返回:
    租金计算结果，包括总租金、违约金（如适用）和可退还押金
    """
    total_rent = monthly_rent * stay_months
    if is_early_termination:
        penalty = monthly_rent * notice_period_months
        refundable_deposit = max(0.0, deposit - penalty)
        return (
            f"🏠 租金计算结果：\n"
            f"- 月租金：S${monthly_rent:.2f}\n"
            f"- 实际居住月数：{stay_months}个月\n"
            f"- 应付租金总额：S${total_rent:.2f}\n"
            f"- 提前退租违约金（{notice_period_months}个月通知期）：S${penalty:.2f}\n"
            f"- 已付押金：S${deposit:.2f}\n"
            f"- 可退还押金：S${refundable_deposit:.2f}\n"
            f"⚠️ 注：违约金计算基于常见租房合同条款，具体以您的合同为准。"
        )
    else:
        refundable_deposit = deposit
        return (
            f"🏠 租金计算结果：\n"
            f"- 月租金：S${monthly_rent:.2f}\n"
            f"- 居住月数：{stay_months}个月\n"
            f"- 应付租金总额：S${total_rent:.2f}\n"
            f"- 已付押金：S${deposit:.2f}\n"
            f"- 可退还押金（无损坏情况下）：S${refundable_deposit:.2f}"
        )

@tool(return_direct=True)
def calculate_moveout_date(current_date: str, notice_days: int = 60) -> str:
    """
    根据提交退租通知的日期和通知期，计算退租截止日期。
    
    参数:
    current_date: 提交退租通知的日期（格式：YYYY-MM-DD，例如2024-05-20）
    notice_days: 退租通知期（单位：天，默认60天）
    
    返回:
    退租日期计算结果，包括通知提交日期、退租截止日期和剩余天数
    """
    try:
        current = datetime.strptime(current_date, "%Y-%m-%d")
        moveout_date = datetime(current.year, current.month, current.day + notice_days)
        days_remaining = (moveout_date - current).days
        return (
            f"📅 退租日期计算结果：\n"
            f"- 通知提交日期：{current.strftime('%Y年%m月%d日')}\n"
            f"- 通知期：{notice_days}天\n"
            f"- 退租截止日期：{moveout_date.strftime('%Y年%m月%d日')}\n"
            f"- 剩余天数：{days_remaining}天\n"
            f"✅ 请在截止日前完成退租检查和钥匙交接。"
        )
    except Exception as e:
        return f"❌ 日期计算错误：{str(e)}，请确保日期格式为YYYY-MM-DD（如2024-05-20）"

@tool(return_direct=True)
def get_repair_responsibility(repair_type: str, cost: float = 0.0) -> str:
    """
    判断不同类型维修的责任方（房东或租户）及费用承担规则。
    
    参数:
    repair_type: 维修类型（例如：空调、灯泡、墙面、水管等）
    cost: 维修费用（单位：新元，可选参数）
    
    返回:
    维修责任划分结果，说明谁承担维修及费用
    """
    repair_type = repair_type.lower()
    if "灯泡" in repair_type or "灯管" in repair_type:
        return f"💡 {repair_type}维修责任：租户承担（需自行更换，费用自付）"
    elif "空调" in repair_type:
        return (
            f"❄️ {repair_type}维修责任：\n"
            f"- 3个月定期保养：房东承担\n"
            f"- 正常损坏维修（非租户导致）：房东承担\n"
            f"- 租户使用不当导致损坏：租户承担\n"
            f"⚠️ 具体以合同约定为准。"
        )
    elif cost > 0:
        if cost <= 200:
            return f"💰 {repair_type}维修（S${cost:.2f}）：租户全额承担（小额维修条款）"
        else:
            tenant_share = 200.0
            landlord_share = cost - 200.0
            return (
                f"💰 {repair_type}维修（S${cost:.2f}）：\n"
                f"- 租户承担：S${tenant_share:.2f}（小额维修起付线）\n"
                f"- 房东承担：S${landlord_share:.2f}\n"
                f"⚠️ 需先获得房东批准，具体以合同为准。"
            )
    elif any(keyword in repair_type for keyword in ["墙面", "屋顶", "水管", "电路", "结构"]):
        return f"🏗️ {repair_type}维修责任：房东承担（属于房屋结构/主体维修）"
    else:
        return f"ℹ️ 未明确{repair_type}的维修责任，请参考租房合同中的「维修条款」或提供更多细节。"

# ---------------------- 3. PDF处理：加载合同并构建RAG知识库 ----------------------
def process_rental_contract(uploaded_file) -> bool:
    if not LANGCHAIN_AVAILABLE:
        st.error("❌ 缺少LangChain依赖，请先安装：pip install langchain-community pypdf faiss-cpu")
        return False
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_file_path = tmp_file.name
        
        loader = PyPDFLoader(tmp_file_path)
        documents = loader.load()
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=st.session_state.model_config["chunk_size"],
            chunk_overlap=st.session_state.model_config["chunk_overlap"],
            length_function=len
        )
        split_docs = text_splitter.split_documents(documents)
        st.session_state.doc_chunk_count = len(split_docs)
        
        embeddings = OpenAIEmbeddings(openai_api_key=os.getenv("OPENAI_API_KEY"))
        vectorstore = FAISS.from_documents(split_docs, embeddings)
        
        llm = ChatOpenAI(
            model_name="gpt-4o-mini",
            temperature=st.session_state.model_config["temperature"],
            max_tokens=st.session_state.model_config["max_tokens"],
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
        memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            output_key="answer"
        )
        conversation_chain = ConversationalRetrievalChain.from_llm(
            llm=llm,
            retriever=vectorstore.as_retriever(search_kwargs={"k": 3}),
            memory=memory,
            return_source_documents=True
        )
        
        tools = [calculate_rent, calculate_moveout_date, get_repair_responsibility]
        agent = initialize_agent(
            tools=tools,
            llm=llm,
            agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
            verbose=False,
            memory=memory
        )
        
        st.session_state.vectorstore = vectorstore
        st.session_state.conversation_chain = conversation_chain
        st.session_state.agent = agent
        st.session_state.uploaded_file = uploaded_file
        st.session_state.uploaded_file_name = uploaded_file.name
        st.session_state.pdf_processed = True
        
        os.unlink(tmp_file_path)
        return True
    
    except Exception as e:
        st.error(f"❌ 合同处理失败：{str(e)}")
        if "tmp_file_path" in locals():
            os.unlink(tmp_file_path)
        return False

# ---------------------- 4. 对话处理：路由问题到RAG或工具 ----------------------
def handle_user_query(query: str) -> str:
    query_lower = query.lower()
    # 工具调用
    tool_keywords = ["计算", "多少钱", "多少天", "截止日期", "维修责任", "谁承担", "押金"]
    if st.session_state.agent and any(keyword in query_lower for keyword in tool_keywords):
        try:
            return st.session_state.agent.run(query)
        except Exception as e:
            st.warning(f"⚠️ 工具调用失败，将尝试从合同中查询：{str(e)}")
    
    # RAG知识库
    contract_keywords = ["合同", "条款", "外交条款", "退租", "入住", "责任", "义务", "权利", "押金"]
    if st.session_state.conversation_chain and (
        st.session_state.uploaded_file or any(keyword in query_lower for keyword in contract_keywords)
    ):
        try:
            response = st.session_state.conversation_chain({"question": query})
            answer = response["answer"]
            source_docs = response.get("source_documents", [])
            if source_docs:
                sources = "\n".join([f"- 第{doc.metadata.get('page', '未知')}页：{doc.page_content[:100]}..." for doc in source_docs[:2]])
                answer += f"\n\n📄 参考合同内容：\n{sources}"
            return answer
        except Exception as e:
            return f"❌ 从合同中查询失败：{str(e)}，请检查合同PDF是否有效。"
    
    # 通用对话 - 优化问候语处理
    llm = ChatOpenAI(
        model_name="gpt-4o-mini",
        temperature=st.session_state.model_config["temperature"],
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )
    
    # 更明确的系统提示词，优化问候语回应
    system_prompt = """你是租房助手，回答需简洁、实用，基于新加坡租房常识（无合同信息时）。
    当用户发送问候语（如"你好"、"您好"等）时，简要回应并引导用户提问租房相关问题，避免重复回复相同内容。"""
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{query}")
    ])
    chain = LLMChain(llm=llm, prompt=prompt)
    return chain.run(query)

# ---------------------- 5. UI组件 ----------------------
def create_upload_interface():
    st.subheader("📄 上传租房合同PDF")
    uploaded_file = st.file_uploader(
        "选择您的租房合同（支持PDF格式）",
        type="pdf",
        disabled=st.session_state.is_thinking,
        help="上传后可基于合同内容回答问题（如外交条款、维修责任等）"
    )
    
    if uploaded_file:
        file_size = uploaded_file.size / 1024
        st.success(f"✅ 已选择文件：{uploaded_file.name}")
        st.info(f"📊 文件信息：{file_size:.1f} KB")
        
        if uploaded_file.name != st.session_state.uploaded_file_name or not st.session_state.pdf_processed:
            with st.spinner("🔄 正在解析合同..."):
                success = process_rental_contract(uploaded_file)
                if success:
                    st.success("✅ 合同解析完成！")
                    st.markdown(f"""
                        • 已生成 {st.session_state.doc_chunk_count} 个文本块；<br>
                        • 可提问：外交条款、维修责任、退租流程等问题；<br>
                        """, unsafe_allow_html=True)
    
    st.subheader("💡 常见问题示例")
    sample_questions = [
        "什么是外交条款？",
        "空调坏了谁负责维修？",
        "维修费用超过200新元谁承担？",
        "退租前需要做哪些准备？",
        "计算月租金3000新元，住10个月的总租金"
    ]
    for idx, question in enumerate(sample_questions):
        if st.button(question, key=f"sample_btn_{idx}", disabled=st.session_state.is_thinking):
            # 检查是否是重复提交
            if question != st.session_state.last_processed_input:
                st.session_state.messages.append({"role": "user", "content": question})
                with st.spinner("🤔 正在整理答案..."):
                    st.session_state.is_thinking = True
                    time.sleep(1)
                    response = handle_user_query(question)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                    st.session_state.is_thinking = False
                st.session_state.last_processed_input = question
                st.session_state.new_message = True
                st.rerun()

def create_sidebar():
    with st.sidebar:
        st.header("🔧 系统配置")
        
        st.subheader("🔑 OpenAI API Key")
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            st.success("✅ API Key已从环境变量加载")
        else:
            user_api_key = st.text_input(
                "输入您的OpenAI API Key",
                type="password",
                help="获取地址：https://platform.openai.com/api-keys"
            )
            if user_api_key:
                os.environ["OPENAI_API_KEY"] = user_api_key
                st.success("✅ API Key已配置，可开始使用！")
            else:
                st.warning("⚠️ 请配置OpenAI API Key，否则无法生成回答。")
        
        st.divider()
        
        st.subheader("🤖 模型设置")
        temperature = st.slider(
            "回答创造性（Temperature）",
            min_value=0.0,
            max_value=1.0,
            value=st.session_state.model_config["temperature"],
            step=0.1,
            help="0.0=严谨（基于合同），1.0=灵活（可能偏离合同）"
        )
        max_tokens = st.slider(
            "回答最大长度（Max Tokens）",
            min_value=500,
            max_value=2000,
            value=st.session_state.model_config["max_tokens"],
            step=100
        )
        
        st.subheader("📄 文档设置")
        chunk_size = st.slider(
            "PDF文本块大小（Chunk Size）",
            min_value=500,
            max_value=2000,
            value=st.session_state.model_config["chunk_size"],
            step=100
        )
        
        st.session_state.model_config.update({
            "temperature": temperature,
            "max_tokens": max_tokens,
            "chunk_size": chunk_size
        })
        
        st.divider()
        
        st.subheader("📋 当前合同状态")
        if st.session_state.pdf_processed and st.session_state.uploaded_file_name:
            st.success(f"已上传合同：《{st.session_state.uploaded_file_name}》")
            st.metric("文本块数量", st.session_state.doc_chunk_count)
        else:
            st.warning("未上传合同，请在左侧上传PDF文件")
        
        if st.button("🗑️ 清空聊天记录", type="secondary"):
            st.session_state.messages = [
                {"role": "assistant", "content": "您好！我是租房助手，可帮您解答合同疑问、维修责任、退租流程等问题。请上传租房合同PDF，或直接提问～"}
            ]
            st.session_state.last_processed_input = None  # 清空最后处理记录
            if st.session_state.conversation_chain:
                st.session_state.conversation_chain.memory.clear()
            if st.session_state.agent:
                st.session_state.agent.memory.clear()
            st.success("✅ 聊天记录已清空！")
            st.rerun()

def display_chat_history():
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    
    for i, msg in enumerate(st.session_state.messages):
        if msg["role"] == "user":
            st.markdown(f"""
            <div class="chat-message user-message">
                <strong>👤 您：</strong><br>{msg['content']}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="chat-message assistant-message">
                <strong>🏠 租房助手：</strong><br>{msg['content']}
            </div>
            """, unsafe_allow_html=True)
        
        if (i + 1) % 5 == 0 and i != len(st.session_state.messages) - 1:
            st.markdown('<hr style="margin: 1rem 0;">', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 处理新消息刷新
    if st.session_state.new_message:
        st.session_state.new_message = False
        st.rerun()

# ---------------------- 6. 主函数 ----------------------
def main():
    setup_custom_css()
    initialize_session_state()
    
    st.markdown('<h1 class="main-header">🏠 租房助手Chatbot</h1>', unsafe_allow_html=True)
    
    create_sidebar()
    col_upload, col_chat = st.columns([1, 2], gap="large")
    
    with col_upload:
        create_upload_interface()
    
    with col_chat:
        st.subheader("💬 聊天窗口")
        display_chat_history()
        
        # 定义输入处理回调函数
        def handle_input():
            user_input = st.session_state.user_input_temp
            if user_input and not st.session_state.is_thinking:
                # 添加用户消息到聊天历史
                st.session_state.messages.append({"role": "user", "content": user_input})
                
                with st.spinner("🤔 正在整理答案..."):
                    st.session_state.is_thinking = True
                    response = handle_user_query(user_input)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                    st.session_state.is_thinking = False
                
                # 清空输入框
                st.session_state.user_input_temp = ""
        
        # 使用带回调的文本输入框
        st.text_input(
            "请输入问题（如：外交条款是什么？）...",
            key="user_input_temp",
            disabled=st.session_state.is_thinking,
            on_change=handle_input  # 输入提交时触发处理
        )

if __name__ == "__main__":
   main()