import json, os, time
import streamlit as st
from utils.user_auth import register_user
from dotenv import load_dotenv

load_dotenv()

# ========== 页面配置 ==========
st.set_page_config(page_title="注册账号 | Smart Rental", page_icon="📝", layout="centered")

# ========== 隐藏所有导航与侧边栏 ==========
st.markdown("""
    <style>
    /* 完全隐藏左侧导航栏和侧边栏 */
    section[data-testid="stSidebar"], 
    section[data-testid="stSidebarNav"], 
    [data-testid="stSidebarHeader"],
    [data-testid="stSidebarNavLink"] {
        display: none !important;
        visibility: hidden !important;
    }
    </style>
""", unsafe_allow_html=True)

# ========== 登录状态保护 ==========
if "user_role" in st.session_state and st.session_state["user_role"]:
    st.warning("⚠️ 您已登录，无需注册新账号。")
    st.switch_page("app.py")

# ========== 页面标题 ==========
st.markdown("""
<div style="text-align:center; margin-bottom: 1rem;">
  <h2 style='color:#2E8B57;'>📝 注册新账号</h2>
  <p style='color:gray;'>请选择注册身份，房东注册需要密钥。</p>
</div>
""", unsafe_allow_html=True)

# ========== 注册表单 ==========
st.subheader("👤 用户信息")

# 选择角色
role_display = st.radio("选择身份", ["租客", "房东"], horizontal=True)
role = "tenants" if role_display == "租客" else "landlords"

# 如果是房东需要输入密钥
if role == "landlords":
    landlord_key = st.text_input("房东注册密钥", type="password")
    if landlord_key and landlord_key != "ilovedss":
        st.error("❌ 房东注册密钥不正确")

username = st.text_input("用户名")
password = st.text_input("密码", type="password")
confirm = st.text_input("确认密码", type="password")
email = st.text_input("邮箱（可选）", placeholder="用于找回密码")

# ========== 注册逻辑 ==========
if st.button("✅ 注册", use_container_width=True, type="primary"):
    if not username or not password:
        st.warning("⚠️ 用户名和密码不能为空。")
    elif password != confirm:
        st.warning("⚠️ 两次输入的密码不一致。")
    elif role == "landlords" and (not landlord_key or landlord_key != "ilovedss"):
        st.error("❌ 请输入正确的房东注册密钥")
    else:
        with st.spinner("正在创建账户..."):
            success, msg = register_user(username, password, role, email)
            if success:
                st.success("✅ 注册成功！请返回登录页面。")
                time.sleep(1)
                st.switch_page("app.py")
            else:
                st.error(msg)

st.markdown("---")

# ========== 返回登录页 ==========
if st.button("⬅️ 返回登录页", use_container_width=True):
    st.switch_page("app.py")

st.markdown("""
<hr>
<p style='text-align:center; color:gray; font-size:0.9em;'>
© 2025 Smart Rental Assistant | NUS DSS5105 Capstone Project
</p>
""", unsafe_allow_html=True)
