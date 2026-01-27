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
    
    DISABLED for local development - always returns True
    
    Returns:
        True (authentication disabled)
    """
    # Authentication disabled for localhost
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
