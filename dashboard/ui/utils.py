import streamlit as st
from datetime import datetime
import pytz
from src.roles.job_price import PriceSpy

@st.cache_resource
def get_spy_instance():
    return PriceSpy()

def to_local_time(utc_str, format='%Y-%m-%d %H:%M'):
    try:
        if not utc_str: return "--:--"
        utc_time = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
        return utc_time.astimezone(pytz.timezone('Asia/Bangkok')).strftime(format)
    except: return utc_str

def get_cfg(db, key, default):
    try:
        res = db.table("bot_config").select("value").eq("key", key).execute()
        return res.data[0]['value'] if res.data else default
    except: return default
