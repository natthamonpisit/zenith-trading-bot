import streamlit as st
import os

st.set_page_config(page_title="Debug Mode")

st.title("✅ Hello World!")
st.success("If you see this, the connection is working!")

st.write(f"Listening on Port: {os.environ.get('PORT', 'Unknown')}")
st.write("Current Directory: " + os.getcwd())
