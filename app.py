import streamlit as st
from utils.user_auth import authenticate_user
from dotenv import load_dotenv
import time
import os

# ========== 初始化配置 ==========
try:
    load_dotenv()
except Exception:
    pass

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

# ✅ 页面跳转函数（稳定写法）
def go_to(page_name: str):
    """
    页面跳转函数。
    支持 /pages/tenant_chat.py、/pages/landlord_portal.py、/pages/register.py。
    """
    try:
        if page_name == "tenant_chat":
            st.switch_page("pages/tenant_chat.py")
        elif page_name == "landlord_portal":
            st.switch_page("pages/landlord_portal.py")
        elif page_name == "register":
            st.switch_page("pages/register.py")
    except Exception as e:
        st.error(f"Navigation error: {e}")

# ========== 登录状态检测 ==========
if st.session_state.user_role == "landlords":
    go_to("landlord_portal")
elif st.session_state.user_role == "tenants":
    go_to("tenant_chat")

# ========== 页面头部 ==========
st.markdown("""
<div style="text-align:center; margin-bottom: 1rem;">
  <h1 style='color:#2E8B57; margin-bottom:0;'>🏠 Smart Rental Assistant</h1>
  <p style='color:gray; font-size:1.05em;'>Login to start using the Smart Rental Assistant</p>
</div>
""", unsafe_allow_html=True)

# ========== 登录表单 ==========
with st.form("login_form", clear_on_submit=False):
    st.markdown("### 🔑 Account Login")
    col1, col2 = st.columns([1.2, 1.8])
    with col1:
        role_display = st.radio("Role:", ["Tenant", "Landlord"], horizontal=True)
    with col2:
        username = st.text_input("Username", placeholder="Enter your username")
        password = st.text_input("Password", type="password", placeholder="Enter your password")

    role_map = {"Tenant": "tenants", "Landlord": "landlords"}
    role = role_map[role_display]

    login_btn = st.form_submit_button("Login", use_container_width=True)

if login_btn:
    if not username or not password:
        st.warning("⚠️ Please enter your username and password.")
    else:
        with st.spinner("Verifying identity..."):
            time.sleep(0.8)
            success, msg = authenticate_user(username, password, role)
            if success:
                st.session_state.username = username
                st.session_state.user_role = role
                st.success("✅ Login successful! Redirecting...")
                time.sleep(1)
                if role == "landlords":
                    go_to("landlord_portal")
                else:
                    go_to("tenant_chat")
            else:
                st.error(msg)

# ========== Registration Area ==========
st.markdown("---")
st.info("Don't have an account? Click the button below to register 👇")

if st.button("📝 Register New Account", use_container_width=True):
    go_to("register")

# ========== 页脚 ==========
st.markdown("""
<hr>
<p style='text-align:center; color:gray; font-size:0.9em;'>
© 2025 Smart Rental Assistant | NUS DSS5105 Capstone Project
</p>
""", unsafe_allow_html=True)
