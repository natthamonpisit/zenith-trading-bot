"""
Authentication module for Streamlit dashboard.

Provides password protection using Streamlit secrets.
"""

import streamlit as st
import hmac


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
        # Timing-safe comparison to prevent timing attacks
        if hmac.compare_digest(
            st.session_state["password"],
            st.secrets["passwords"]["admin"]
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
        st.info("💡 Set your password in `.streamlit/secrets.toml`")
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
