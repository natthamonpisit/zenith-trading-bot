"""
Authentication module for Streamlit dashboard.

Provides password protection using Streamlit secrets or environment variables.
"""

import streamlit as st
import hmac
import os


def get_admin_password() -> str:
    """
    Get admin password from secrets.toml or environment variable.
    
    Priority:
    1. Streamlit secrets (local development)
    2. Environment variable ADMIN_PASSWORD (Railway/production)
    
    Returns:
        Admin password string
    """
    try:
        # Try Streamlit secrets first (local)
        password = st.secrets["passwords"]["admin"]
        st.sidebar.info(f"🔑 Password source: Streamlit Secrets (length: {len(password)})")
        return password
    except (KeyError, FileNotFoundError) as e:
        # Fallback to environment variable (Railway)
        password = os.environ.get("ADMIN_PASSWORD")
        if not password:
            st.error("⚠️ No password configured! Set ADMIN_PASSWORD environment variable or secrets.toml")
            st.error(f"Debug: Error from secrets = {type(e).__name__}: {e}")
            st.stop()
        st.sidebar.warning(f"🔑 Password source: Environment Variable (length: {len(password)})")
        return password


def check_password() -> bool:
    """
    Check if user has entered correct password.
    
    Returns:
        True if password is correct, False otherwise
        
    Usage:
        if not check_password():
            st.stop()  # Stop execution if not authenticated
    """
    
    # DEBUG: Show current auth state
    with st.sidebar:
        st.markdown("### 🔐 Auth Status")
        auth_state = st.session_state.get("password_correct", "NOT_SET")
        st.markdown(f"**Current State:** `{auth_state}`")
    
    # IMPORTANT: Check authentication FIRST before showing login form
    # This ensures authenticated users don't see login screen on rerun
    if st.session_state.get("password_correct") == True:
        st.sidebar.success("✅ Authenticated - Bypassing login")
        return True
    
    def password_entered():
        """Callback when password is submitted"""
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 🐛 DEBUG INFO")
        
        # Safety check: ensure password key exists
        if "password" not in st.session_state:
            st.sidebar.error("❌ Password key NOT in session_state")
            st.session_state["password_correct"] = False
            return
        
        st.sidebar.success(f"✅ Password entered (length: {len(st.session_state['password'])})")
            
        # Get configured password
        admin_password = get_admin_password()
        
        st.sidebar.info(f"🔍 Comparing passwords...")
        st.sidebar.code(f"Entered: {st.session_state['password'][:3]}***")
        st.sidebar.code(f"Expected: {admin_password[:3]}***")
        
        # Timing-safe comparison to prevent timing attacks
        if hmac.compare_digest(
            st.session_state["password"],
            admin_password
        ):
            st.sidebar.success("✅ Password MATCH!")
            st.session_state["password_correct"] = True
            # Security: Don't store password in session
            del st.session_state["password"]
        else:
            st.sidebar.error("❌ Password MISMATCH!")
            st.session_state["password_correct"] = False
        
        st.sidebar.markdown(f"**Session State:** `password_correct = {st.session_state.get('password_correct')}`")

    # Password incorrect: show error + retry
    if st.session_state.get("password_correct") == False:
        st.markdown("### 🔐 Zenith Trading Bot - Login")
        st.text_input(
            "Password", 
            type="password", 
            on_change=password_entered,
            key="password"
        )
        st.error("😕 Incorrect password. Please try again.")
        return False
    
    # First run: show login form
    else:
        st.markdown("### 🔐 Zenith Trading Bot - Login")
        st.text_input(
            "Password", 
            type="password", 
            on_change=password_entered,
            key="password",
            help="Enter your dashboard password"
        )
        st.info("💡 **Streamlit Cloud:** Set secrets in App Settings | **Local:** Set in `.streamlit/secrets.toml`")
        return False


def logout():
    """
    Logout current user by clearing session state.
    
    Usage:
        if st.sidebar.button("Logout"):
            logout()
            st.rerun()
    """
    if "password_correct" in st.session_state:
        del st.session_state["password_correct"]


def show_logout_button():
    """
    Show logout button in sidebar.
    
    Returns:
        True if user clicked logout
    """
    if st.sidebar.button("🚪 Logout", help="Logout from dashboard"):
        logout()
        st.rerun()
        return True
    return False
