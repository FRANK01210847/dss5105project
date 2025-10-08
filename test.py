#!/usr/bin/env python3
"""
租房助手Chatbot（模拟测试版）：修复白屏问题
基于Capstone_Project.pdf需求，采用test2的无刷新逻辑
运行命令：streamlit run rental_assistant_mock.py
"""
import streamlit as st
import time

# 页面配置（优先执行）
st.set_page_config(
    page_title="租房助手Chatbot（模拟测试版）",
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
            {"role": "assistant", "content": "您好！我是租房助手（模拟测试版），可帮您解答合同疑问、维修责任、退租流程等问题（基于Capstone_Project.pdf条款）。请上传租房合同PDF，或直接提问～"}
        ]
    if "uploaded_file" not in st.session_state:
        st.session_state.uploaded_file = None
    if "uploaded_file_name" not in st.session_state:
        st.session_state.uploaded_file_name = None
    if "pdf_processed" not in st.session_state:
        st.session_state.pdf_processed = False
    if "doc_chunk_count" not in st.session_state:
        st.session_state.doc_chunk_count = 15
    if "is_thinking" not in st.session_state:
        st.session_state.is_thinking = False
    if "new_message" not in st.session_state:  # 新增：标记新消息
        st.session_state.new_message = False

# ---------------------- 2. 模拟PDF处理 ----------------------
def mock_process_pdf(uploaded_file) -> bool:
    try:
        time.sleep(1)
        st.session_state.uploaded_file_name = uploaded_file.name
        st.session_state.pdf_processed = True
        return True
    except Exception as e:
        st.error(f"❌ 合同处理失败（模拟）：{str(e)}")
        return False

# ---------------------- 3. 模拟对话处理 ----------------------
def mock_handle_query(query: str) -> str:
    query_lower = query.lower()
    
    if "外交条款" in query_lower or "diplomatic clause" in query_lower:
        return """
        <span class="test-note">模拟回答（基于Capstone_Project.pdf）</span><br>
        您可在租赁满12个月后，满足以下条件时终止合同：<br>
        • 被驱逐出境、工作/居住许可被拒绝，或被调往新加坡境外；<br>
        • 需提前2个月书面通知房东，或支付2个月租金作为“替代通知”；<br>
        • 必须提供相关证明文件（如公司调令、移民局拒签信）；<br>
        • 若使用此条款终止合同，需按“未履行租期比例”退还房东的代理佣金；<br>
        ⚠️ 重要：续约期间无外交条款，除非房东与租户双方书面同意。<br>
        📄 条款来源：Capstone_Project.pdf Clause 5(c)、5(d)、5(f)
        """
    
    elif "维修" in query_lower or "repair" in query_lower or "坏了" in query_lower:
        if "空调" in query_lower:
            return """
            <span class="test-note">模拟回答（基于Capstone_Project.pdf）</span><br>
            空调维修责任划分规则：<br>
            • 每3个月定期保养：由房东承担全部费用；<br>
            • 正常损坏维修（如部件老化、制冷故障）：房东承担费用；<br>
            • 租户使用不当导致损坏（如液体泼洒、撞击）：租户承担全部费用；<br>
            • 维修前需提前获得房东书面批准，避免后续纠纷。<br>
            📄 条款来源：Capstone_Project.pdf Clause 2(j)
            """
        elif "费用" in query_lower or "钱" in query_lower:
            return """
            <span class="test-note">模拟回答（基于Capstone_Project.pdf）</span><br>
            维修费用承担通用规则：<br>
            • 小额维修（单次/单项≤S$200）：租户全额承担；<br>
            • 大额维修（单次/单项>S$200）：租户承担前S$200，剩余部分由房东承担；<br>
            • 灯泡/灯管更换：租户自行承担费用并更换；<br>
            • 房屋结构维修（屋顶、墙面、主水管、主电路）：房东全额承担；<br>
            • 正常损耗（如衣柜老化、热水器故障）：房东承担费用。<br>
            📄 条款来源：Capstone_Project.pdf Clause 2(g)、2(i)、2(k)、4(c)
            """
    
    elif "退租" in query_lower or "move out" in query_lower or "交还" in query_lower:
        if "清单" in query_lower or "准备" in query_lower or "做什么" in query_lower:
            return """
            <span class="test-note">模拟回答（基于Capstone_Project.pdf）</span><br>
            退租前必须完成的准备清单：<br>
            ✅ 对房屋进行“专业清洁”，需达到入住时的清洁标准；<br>
            ✅ 干洗所有窗帘（需保留干洗凭证）；<br>
            ✅ 移除墙面所有钉子、螺丝、挂钩，并使用白色腻子修补孔洞；<br>
            ✅ 确保房屋无损坏（正常使用损耗除外），无需重新粉刷；<br>
            ✅ 与房东完成“联合检查”，确认房屋状态并签字；<br>
            ✅ 交还所有房屋钥匙、门禁卡及合同约定的家具。<br>
            💡 利好政策：联合检查后若需维修，维修期间租户无需支付租金。<br>
            📄 条款来源：Capstone_Project.pdf Clause 2(y)、2(z)、6(o)
            """
    
    elif "合同" in query_lower or "pdf" in query_lower or "文件" in query_lower:
        if st.session_state.pdf_processed and st.session_state.uploaded_file_name:
            return f"""
            <span class="test-note">模拟回答（基于Capstone_Project.pdf）</span><br>
            当前合同状态：<br>
            • 已上传合同：《{st.session_state.uploaded_file_name}》；<br>
            • 模拟解析结果：生成{st.session_state.doc_chunk_count}个文本块；<br>
            • 可提问范围：外交条款、维修责任、退租流程等合同相关问题；<br>
            """
        else:
            return """
            <span class="test-note">模拟回答（基于Capstone_Project.pdf）</span><br>
            合同状态提示：<br>
            • 暂未上传或解析合同，请在左侧“上传租房合同PDF”区域选择文件；<br>
            • 支持文件格式：.pdf（建议单个文件≤10MB）；<br>
            """
    
    else:
        return """
        <span class="test-note">模拟回答（基于Capstone_Project.pdf）</span><br>
        已接收您的问题，当前可解答以下核心问题：<br>
        • 合同类：什么是外交条款？<br>
        • 维修类：空调坏了谁负责？维修费用超过200新元谁承担？<br>
        • 退租类：退租前需要做哪些准备？
        """

# ---------------------- 4. UI组件 ----------------------
def create_upload_interface():
    st.subheader("📄 上传租房合同PDF（模拟流程）")
    uploaded_file = st.file_uploader(
        "选择合同文件（示例：Peter_Tenancy_Agreement.pdf）",
        type="pdf",
        disabled=st.session_state.is_thinking
    )
    
    if uploaded_file:
         # 显示文件基础信息（只保留大小，删除last_modified）
        file_size = uploaded_file.size / 1024  # 转换为KB
        st.success(f"✅ 已选择文件：{uploaded_file.name}")
        # 移除对last_modified的引用
        st.info(f"📊 文件信息：{file_size:.1f} KB")
        
        if uploaded_file.name != st.session_state.uploaded_file_name or not st.session_state.pdf_processed:
            with st.spinner("🔄 正在解析合同..."):
                if mock_process_pdf(uploaded_file):
                    st.success("✅ 合同解析完成（模拟）！")
                    st.markdown(f"""
                        • 已生成 {st.session_state.doc_chunk_count} 个文本块（符合合同文档长度）；<br>
                        • 可提问：外交条款、维修责任、退租流程等问题；<br>
                        • 参考来源：Capstone_Project.pdf “Core Use Case (Tenant Chatbot)”需求
                        """, unsafe_allow_html=True)
    
    st.subheader("💡 文档核心问题示例")
    sample_questions = [
        "什么是外交条款？",
        "空调坏了谁负责维修？",
        "维修费用超过200新元谁承担？",
        "退租前需要做哪些准备？",
        "当前上传的合同处理好了吗？"
    ]
    for idx, question in enumerate(sample_questions):
        if st.button(question, key=f"sample_btn_{idx}", disabled=st.session_state.is_thinking):
            st.session_state.messages.append({"role": "user", "content": question})
            response = mock_handle_query(question)
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.session_state.new_message = True  # 标记新消息

def create_sidebar():
    with st.sidebar:
        st.header("🔧 系统状态（模拟测试版）")
        
        st.subheader("🔑 API Key状态")
        st.success("✅ 模拟测试版无需配置API Key")
        
        st.subheader("📋 当前合同状态")
        if st.session_state.pdf_processed and st.session_state.uploaded_file_name:
            st.success(f"已上传合同：《{st.session_state.uploaded_file_name}》")
            st.metric("模拟文本块数量", st.session_state.doc_chunk_count)
        else:
            st.warning("未上传合同，请在左侧上传PDF文件")
        
        if st.button("🗑️ 清空聊天记录", type="secondary"):
            st.session_state.messages = [
                {"role": "assistant", "content": "您好！我是租房助手（模拟测试版），可帮您解答合同疑问、维修责任、退租流程等问题（基于Capstone_Project.pdf条款）。请上传租房合同PDF，或直接提问～"}
            ]
            st.success("✅ 聊天记录已清空！")
        
        st.subheader("📝 测试指南")
        st.markdown("""
        需验证的核心流程：
        1. PDF上传流程：选择文件→查看信息→确认解析完成；
        2. 按钮触发流程：点击示例问题→自动添加到聊天记录；
        3. 聊天交互流程：手动输入问题→查看模拟回答；
        4. 状态重置流程：清空聊天记录→恢复初始状态。
        """)

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
                <strong>🏠 租房助手（模拟）：</strong><br>{msg['content']}
            </div>
            """, unsafe_allow_html=True)
        
        if (i + 1) % 5 == 0 and i != len(st.session_state.messages) - 1:
            st.markdown('<hr style="margin: 1rem 0;">', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------- 5. 主函数 ----------------------
def main():
    setup_custom_css()
    initialize_session_state()
    
    st.markdown('<h1 class="main-header">🏠 租房助手Chatbot（模拟测试版）</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center; color:#666;">基于Capstone_Project.pdf Tenant Chatbot需求设计</p>', unsafe_allow_html=True)
    
    create_sidebar()
    col_upload, col_chat = st.columns([1, 2], gap="large")
    
    with col_upload:
        create_upload_interface()
    
    with col_chat:
        st.subheader("💬 聊天窗口（基于Capstone_Project.pdf条款）")
        display_chat_history()
        
        user_input = st.text_input(
            "请输入问题（如：外交条款是什么？）...",
            key="user_input",
            disabled=st.session_state.is_thinking
        )
        
        if user_input:
            st.session_state.messages.append({"role": "user", "content": user_input})
            
            with st.spinner("🤔 正在整理答案..."):
                st.session_state.is_thinking = True
                time.sleep(1)
                response = mock_handle_query(user_input)
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.session_state.is_thinking = False
            
            st.session_state.new_message = True  # 标记新消息

if __name__ == "__main__":
    main()