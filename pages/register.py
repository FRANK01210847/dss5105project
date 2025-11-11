import json, os, time
import streamlit as st
from utils.user_auth import register_user
from dotenv import load_dotenv

load_dotenv()

# ========== 页面配置 ==========
st.set_page_config(page_title="Register | Smart Rental", page_icon="📝", layout="centered")

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
    st.warning("⚠️ Already logged in. Redirecting to main app...")
    st.switch_page("app.py")

# ========== 页面标题 ==========
st.markdown("""
<div style="text-align:center; margin-bottom: 1rem;">
  <h2 style='color:#2E8B57;'>📝 Register New Account</h2>
  <p style='color:gray;'>Please select a registration role. Landlord registration requires a key.</p>
</div>
""", unsafe_allow_html=True)

# ========== 注册表单 ==========
st.subheader("👤 User Information")

# 选择角色
role_display = st.radio("Select Role", ["Tenant", "Landlord"], horizontal=True)
role = "tenants" if role_display == "Tenant" else "landlords"

# 如果是房东需要输入密钥
if role == "landlords":
    landlord_key = st.text_input("Landlord Registration Key", type="password")
    if landlord_key and landlord_key != "ilovedss":
        st.error("❌ Invalid landlord registration key.")

username = st.text_input("Username")
password = st.text_input("Password", type="password")
confirm = st.text_input("Confirm Password", type="password")
email = st.text_input("Email (Optional)", placeholder="For password recovery")

# ========== 注册逻辑 ==========
if st.button("✅ Register", use_container_width=True, type="primary"):
    if not username or not password:
        st.warning("⚠️ Username and password cannot be empty.")
    elif password != confirm:
        st.warning("⚠️ Passwords do not match.")
    elif role == "landlords" and (not landlord_key or landlord_key != "ilovedss"):
        st.error("❌ Invalid landlord registration key.")
    else:
        with st.spinner("Creating account..."):
            success, msg = register_user(username, password, role, email)
            if success:
                st.success("✅ Registration successful! Please return to the login page.")
                time.sleep(1)
                st.switch_page("app.py")
            else:
                st.error(msg)

st.markdown("---")

# ========== 返回登录页 ==========
if st.button("⬅️ Back to Login Page", use_container_width=True):
    st.switch_page("app.py")

st.markdown("""
<hr>
<p style='text-align:center; color:gray; font-size:0.9em;'>
© 2025 Smart Rental Assistant | NUS DSS5105 Capstone Project
</p>
""", unsafe_allow_html=True)
