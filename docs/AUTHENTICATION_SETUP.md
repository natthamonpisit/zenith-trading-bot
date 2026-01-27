# Streamlit Authentication Setup Guide

## Overview
The Zenith Trading Bot dashboard is now protected with password authentication using Streamlit secrets.

---

## 🔐 How to Set Your Password

### Step 1: Copy the Template
```bash
cd /Users/natthamonpisit/Coding/zenith-trading-bot
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

### Step 2: Edit Your Secrets
Open `.streamlit/secrets.toml` and change the default password:

```toml
[passwords]
admin = "your_unique_secure_password_here"  # ⚠️ CHANGE THIS!
```

**Password Tips**:
- Use at least 12 characters
- Mix uppercase, lowercase, numbers, symbols
- Don't reuse passwords from other services
- Example: `Zen!th2024$Tr@de`

### Step 3: (Optional) Add Other Secrets
You can also move your API keys to secrets.toml:

```toml
[supabase]
url = "https://your-project.supabase.co"
key = "your_anon_key"

[binance]
api_key = "your_api_key"
secret = "your_secret"

[gemini]
api_key = "your_gemini_key"
```

---

## 🚀 How to Use

### Start Dashboard
```bash
streamlit run dashboard/app.py
```

### Login
1. Open browser → `http://localhost:8501`
2. Enter your password
3. Access granted! 🎉

### Logout
Click **"🚪 Logout"** button in the sidebar

---

## ⚠️ Security Notes

### ✅ DO:
- ✅ Keep secrets.toml LOCAL only
- ✅ Use a strong, unique password
- ✅ Share access carefully
- ✅ Change password if compromised

### ❌ DON'T:
- ❌ Commit secrets.toml to Git (auto-ignored)
- ❌ Share secrets.toml file
- ❌ Use weak passwords like "password123"
- ❌ Reuse passwords from other sites

---

## 🔧 Troubleshooting

### "No secrets.toml found"
**Solution**: Copy the template file
```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

### "Password incorrect" every time
**Solution**: Check for typos in secrets.toml. Password is case-sensitive!

### Forgot password?
**Solution**: Edit `.streamlit/secrets.toml` and set a new one

---

## 🔐 How It Works

1. **Timing-Safe Comparison**: Uses `hmac.compare_digest()` to prevent timing attacks
2. **Session-Based**: Password stored in Streamlit session (not in code)
3. **No Database**: Credentials in local file only
4. **Simple & Secure**: Industry-standard practice for Streamlit apps

---

## 🆙 Future Enhancements

Want more security? You can upgrade to:
- Multi-user support (different passwords per user)
- 2FA (two-factor authentication)
- SSO (Single Sign-On) with Google/GitHub
- IP whitelist
- Session timeout

Let me know if you want any of these! 😊
