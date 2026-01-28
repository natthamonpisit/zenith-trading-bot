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
    
    # Show login form
    st.markdown("### 🔐 Zenith Trading Bot - Login")
    
    # Use st.form to preserve state better than callback
    with st.form("login_form"):
        password_input = st.text_input(
            "Password", 
            type="password",
            help="Enter your dashboard password"
        )
        submit_button = st.form_submit_button("Login")
        
        if submit_button:
            with st.sidebar:
                st.markdown("---")
                st.markdown("### 🐛 DEBUG INFO")
                st.sidebar.success(f"✅ Password entered (length: {len(password_input)})")
            
            # Get configured password
            admin_password = get_admin_password()
            
            with st.sidebar:
                st.sidebar.info(f"🔍 Comparing passwords...")
                st.sidebar.code(f"Entered: {password_input[:3]}***")
                st.sidebar.code(f"Expected: {admin_password[:3]}***")
            
            # Timing-safe comparison to prevent timing attacks
            if hmac.compare_digest(password_input, admin_password):
                st.sidebar.success("✅ Password MATCH!")
                st.session_state["password_correct"] = True
                st.rerun()  # Rerun to show dashboard
            else:
                st.sidebar.error("❌ Password MISMATCH!")
                st.session_state["password_correct"] = False
                st.error("😕 Incorrect password. Please try again.")
    
    # Show info only on first load
    if st.session_state.get("password_correct") is None:
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
