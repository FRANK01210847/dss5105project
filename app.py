import streamlit as st
from utils.user_auth import authenticate_user
from dotenv import load_dotenv
import time
import os

# ========== 初始化配置 ==========
load_dotenv()
st.set_page_config(page_title="🏠 Smart Rental Assistant", page_icon="🏠", layout="centered")

# 隐藏默认侧边栏
st.markdown("""
    <style>
    [data-testid="stSidebar"] {display: none;}
    .block-container {padding-top: 3rem;}
    div.stButton > button:first-child {
        background-color: #2E8B57;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 0.6em 1.2em;
        font-weight: 600;
    }
    div.stButton > button:first-child:hover {
        background-color: #3CB371;
        color: white;
    }
    hr {
        border: none;
        border-top: 1px solid #ccc;
        margin: 1.5em 0;
    }
    </style>
""", unsafe_allow_html=True)

# ========== Session 初始化 ==========
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "username" not in st.session_state:
    st.session_state.username = None

# ========== 登录状态检测 ==========
if st.session_state.user_role == "landlords":
    st.switch_page("pages/landlord_portal.py")
elif st.session_state.user_role == "tenants":
    st.switch_page("pages/tenant_chat.py")

# ========== 页面头部 ==========
st.markdown("""
<div style="text-align:center; margin-bottom: 1rem;">
  <h1 style='color:#2E8B57; margin-bottom:0;'>🏠 Smart Rental Assistant</h1>
  <p style='color:gray; font-size:1.05em;'>登录以开始使用智能租房助手</p>
</div>
""", unsafe_allow_html=True)

# ========== 登录表单 ==========
with st.form("login_form", clear_on_submit=False):
    st.markdown("### 🔑 登录账号")
    col1, col2 = st.columns([1.2, 1.8])
    with col1:
        role_display = st.radio("身份：", ["租客", "房东"], horizontal=True)
    with col2:
        username = st.text_input("用户名", placeholder="请输入用户名")
        password = st.text_input("密码", type="password", placeholder="请输入密码")

    role_map = {"租客": "tenants", "房东": "landlords"}
    role = role_map[role_display]

    login_btn = st.form_submit_button("登录", use_container_width=True)

if login_btn:
    if not username or not password:
        st.warning("⚠️ 请输入用户名和密码。")
    else:
        with st.spinner("正在验证身份..."):
            time.sleep(0.8)
            success, msg = authenticate_user(username, password, role)
            if success:
                st.session_state.username = username
                st.session_state.user_role = role
                st.success("✅ 登录成功！正在跳转...")
                time.sleep(1)
                if role == "landlords":
                    st.switch_page("pages/landlord_portal.py")
                else:
                    st.switch_page("pages/tenant_chat.py")
            else:
                st.error(msg)

# ========== 注册区域 ==========
st.markdown("---")
st.info("还没有账号？点击下方按钮注册 👇")

if st.button("📝 注册新账号", use_container_width=True):
    st.switch_page("pages/register.py")

# ========== 页脚 ==========
st.markdown("""
<hr>
<p style='text-align:center; color:gray; font-size:0.9em;'>
© 2025 Smart Rental Assistant | NUS DSS5105 Capstone Project
</p>
""", unsafe_allow_html=True)
