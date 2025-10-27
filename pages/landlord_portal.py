import os, json, time
import streamlit as st
import qrcode
from io import BytesIO
from dotenv import load_dotenv
from utils.rag_utils import build_vectorstore_from_pdf, save_vectorstore
from langchain_community.chat_models import ChatOpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader

load_dotenv()
st.set_page_config(page_title="房东管理 | Smart Rental", page_icon="🗄️", layout="wide")
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

st.markdown("""<style>section[data-testid="stSidebarNav"]{display:none;}</style>""", unsafe_allow_html=True)

# 权限
if st.session_state.get("user_role") != "landlords":
    st.warning("请先以【房东】身份登录。")
    st.switch_page("app.py")

# 顶部品牌栏
st.markdown("""
<div style="background:#2E8B57;padding:12px 16px;border-radius:12px;margin-bottom:16px;">
  <h3 style="color:#fff;margin:0;">🗄️ 房东管理系统</h3>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.write(f"👋 欢迎：**{st.session_state.get('username','-')}**")
    if st.button("🚪 登出", use_container_width=True):
        st.session_state.clear(); st.switch_page("app.py")
    if os.getenv("OPENAI_API_KEY"): st.success("✅ OpenAI Key 正常")
    else: 
        key = st.text_input("OpenAI API Key", type="password")
        if key: os.environ["OPENAI_API_KEY"]=key; st.success("✅ 已设置")

st.markdown("### 上传合同 → 入库")
c1, c2 = st.columns([1.2, 1.8], gap="large")

with c1:
    with st.container():
        property_id = st.text_input("🏠 租约编号（唯一）", placeholder="如 MSH2025-001")
        tenant_name = st.text_input("👤 租客姓名", placeholder="如 Ken")
        monthly_rent = st.number_input("💰 月租金（新元）", min_value=0, step=50)
        version_note = st.text_input("📝 版本备注（可选）", placeholder="如 首版 / 调整押金等")
        cloud_link = st.text_input("☁️ 文件云端链接（可选）", placeholder="如 OneDrive/iCloud 分享链接")
        up = st.file_uploader("📄 上传租房合同 PDF", type=["pdf"])
        if st.button("保存到数据库", type="primary", use_container_width=True):
            if not (property_id and up):
                st.error("请填写租约编号并上传合同。")
            else:
                save_dir = os.path.join("db", property_id)
                
                # 如果存在同名租约，显示对比信息
                if os.path.exists(save_dir):
                    st.warning("⚠️ 检测到同名租约，正在分析新旧合同差异...")
                    
                    try:
                        # 读取旧合同内容
                        old_pdf_path = os.path.join(save_dir, "contract.pdf")
                        old_text = ""
                        if os.path.exists(old_pdf_path):
                            old_loader = PyPDFLoader(old_pdf_path)
                            old_pages = old_loader.load()
                            old_text = "\n".join(page.page_content for page in old_pages)

                        # 获取新合同内容
                        temp_path = os.path.join(save_dir, "temp_new.pdf")
                        with open(temp_path, "wb") as f:
                            f.write(up.getvalue())
                        new_loader = PyPDFLoader(temp_path)
                        new_pages = new_loader.load()
                        new_text = "\n".join(page.page_content for page in new_pages)

                        # 使用 ChatGPT 分析差异
                        llm = ChatOpenAI(
                            model_name="gpt-4o-mini",
                            temperature=0,
                            openai_api_key=os.getenv("OPENAI_API_KEY")
                        )
                        
                        analysis_prompt = f"""
                        请分析以下两份租房合同的主要差异，重点关注：
                        1. 租金金额变化
                        2. 租期变化
                        3. 押金变化
                        4. 其他重要条款的变化

                        旧合同内容：
                        {old_text}

                        新合同内容：
                        {new_text}

                        请用中文总结主要变化，并以表格形式展示关键数据的对比。
                        如果某些信息无法从合同中提取，请注明"无法确定"。
                        """

                        with st.spinner("AI正在分析合同差异..."):
                            analysis = llm.predict(analysis_prompt)
                            st.markdown("### 📄 合同差异分析")
                            st.markdown(analysis)
                        
                        # 清理临时文件
                        if os.path.exists(temp_path):
                            os.remove(temp_path)

                    except Exception as e:
                        st.error(f"❌ 合同分析失败：{str(e)}")
                        st.info("请人工仔细核对合同内容的差异。")
                    
                    # 确认覆盖按钮
                    if st.button("✅ 确认覆盖旧合同", type="primary"):
                        os.makedirs(save_dir, exist_ok=True)
                # 保存原始 PDF 文件
                pdf_path = os.path.join(save_dir, "contract.pdf")
                with open(pdf_path, "wb") as f:
                    f.write(up.getvalue())

                with st.spinner("解析并构建索引..."):
                    vs = build_vectorstore_from_pdf(up, openai_api_key=os.getenv("OPENAI_API_KEY"))
                    save_vectorstore(vs, save_dir)
                # 如果有云端链接，生成二维码
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
                        
                        # 保存二维码图片
                        qr_filename = "contract_qr.png"
                        qr_path = os.path.join(save_dir, qr_filename)
                        img.save(qr_path)
                    except Exception as e:
                        st.warning(f"二维码生成失败：{str(e)}")
                
                # 记录更新历史
                old_version_time = None
                if os.path.exists(save_dir):
                    old_meta_path = os.path.join(save_dir, "metadata.json")
                    if os.path.exists(old_meta_path):
                        try:
                            with open(old_meta_path, "r", encoding="utf-8") as f:
                                old_meta = json.load(f)
                                old_version_time = old_meta.get("last_updated")
                        except:
                            pass

                meta = {
                    "property_id": property_id,
                    "tenant_name": tenant_name,
                    "monthly_rent": monthly_rent,
                    "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "version_note": version_note or "v1",
                    "cloud_link": cloud_link if cloud_link else "",
                    "qr_code": qr_filename if qr_filename else "",
                    "previous_version": old_version_time
                }
                with open(os.path.join(save_dir, "metadata.json"), "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
                st.success(f"✅ 入库成功：{property_id}")
                
                # 显示元数据和二维码
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.json(meta)
                if qr_filename:
                    with col2:
                        st.image(os.path.join(save_dir, qr_filename), caption="合同云端链接二维码")

with c2:
    st.markdown("#### 📂 已入库的租约")
    
    # 初始化删除确认状态
    if "delete_confirm" not in st.session_state:
        st.session_state.delete_confirm = None
        
    rows=[]
    if os.path.isdir("db"):
        for name in sorted(os.listdir("db")):
            p = os.path.join("db", name)
            if os.path.isdir(p):
                meta_path = os.path.join(p, "metadata.json")
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            m = json.load(f)
                        rows.append([
                            name,                           # 租约编号
                            m.get("tenant_name","?"),       # 租客
                            m.get("monthly_rent","?"),      # 月租
                            m.get("last_updated","?"),      # 更新时间
                            m.get("version_note","-"),      # 备注
                            "✅ 有" if m.get("cloud_link") else "❌ 无",  # 云端链接状态
                            name                            # ID用于删除按钮
                        ])
                    except json.JSONDecodeError:
                        st.warning(f"⚠️ 跳过损坏的元数据文件：{meta_path}")
    if rows:
        # 创建表格头部
        header_cols = st.columns([1.2, 1, 1, 1.2, 1, 0.8, 0.8])
        with header_cols[0]:
            st.markdown("**租约编号**")
        with header_cols[1]:
            st.markdown("**租客**")
        with header_cols[2]:
            st.markdown("**月租**")
        with header_cols[3]:
            st.markdown("**更新时间**")
        with header_cols[4]:
            st.markdown("**备注**")
        with header_cols[5]:
            st.markdown("**云链接**")
        with header_cols[6]:
            st.markdown("**操作**")
        
        st.markdown("---")
        
        # 创建表格内容
        for r in rows:
            col1, col2, col3, col4, col5, col6, col7 = st.columns([1.2, 1, 1, 1.2, 1, 0.8, 0.8])
            with col1:
                st.text(r[0])  # 租约编号
            with col2:
                st.text(r[1])  # 租客
            with col3:
                st.text(f"S${r[2]}")  # 月租
            with col4:
                st.text(r[3])  # 更新时间
            with col5:
                st.text(r[4])  # 备注
            with col6:
                st.text(r[5])  # 云端链接状态
            with col7:
                # 删除按钮
                if st.button("🗑️", key=f"del_{r[6]}", help=f"删除租约 {r[0]}"):
                    st.session_state.delete_confirm = r[5]
                    
        # 删除确认对话框
        if st.session_state.delete_confirm:
            contract_id = st.session_state.delete_confirm
            st.warning(f"⚠️ 确定要删除租约 {contract_id} 吗？此操作不可撤销！")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ 确认删除"):
                    contract_path = os.path.join("db", contract_id)
                    try:
                        import shutil
                        shutil.rmtree(contract_path)
                        st.success(f"✅ 已删除租约：{contract_id}")
                        st.session_state.delete_confirm = None
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 删除失败：{str(e)}")
            with col2:
                if st.button("❌ 取消"):
                    st.session_state.delete_confirm = None
                    st.rerun()
    else:
        st.info("当前还没有任何租约，请先上传。")
