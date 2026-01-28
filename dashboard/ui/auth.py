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
        return st.secrets["passwords"]["admin"]
    except (KeyError, FileNotFoundError):
        # Fallback to environment variable (Railway)
        password = os.environ.get("ADMIN_PASSWORD")
        if not password:
            st.error("⚠️ No password configured! Set ADMIN_PASSWORD environment variable or secrets.toml")
            st.stop()
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
    
    def password_entered():
        """Callback when password is submitted"""
        # Safety check: ensure password key exists
        if "password" not in st.session_state:
            st.session_state["password_correct"] = False
            return
            
        # Get configured password
        admin_password = get_admin_password()
        
        # Timing-safe comparison to prevent timing attacks
        if hmac.compare_digest(
            st.session_state["password"],
            admin_password
        ):
            st.session_state["password_correct"] = True
            # Security: Don't store password in session
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    # First run: show login form
    if "password_correct" not in st.session_state:
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
    
    # Password incorrect: show error + retry
    elif not st.session_state["password_correct"]:
        st.markdown("### 🔐 Zenith Trading Bot - Login")
        st.text_input(
            "Password", 
            type="password", 
            on_change=password_entered,
            key="password"
        )
        st.error("😕 Incorrect password. Please try again.")
        return False
    
    # Password correct: authenticated
    else:
        return True


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
