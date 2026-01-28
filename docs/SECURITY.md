# Security Best Practices

## 🔐 Protecting API Keys

### What Happened?
Google detected an exposed Gemini API key in our Git history and automatically revoked it.

### How to Prevent This:

#### 1. **Never Commit Secrets**
- ✅ Use `.env` files (already in `.gitignore`)
- ✅ Store secrets in environment variables
- ❌ NEVER hardcode API keys in code
- ❌ NEVER commit `.env` files

#### 2. **Pre-Commit Hook Installed**
We've installed a pre-commit hook that scans for:
- Google API keys (AIza...)
- OpenAI keys (sk-...)
- AWS keys
- Passwords in code
- Other sensitive patterns

**It will BLOCK your commit if secrets are detected!**

#### 3. **If You Accidentally Commit a Secret:**

**Option A: If not pushed yet**
```bash
# Remove from last commit
git rm --cached .env
git commit --amend
```

**Option B: If already pushed (CRITICAL)**
```bash
# 1. Immediately revoke the key (Google AI Studio, Binance, etc.)
# 2. Create new key
# 3. Update in Railway/Streamlit environment variables
# 4. (Optional) Clean Git history - use BFG Repo Cleaner or git-filter-repo
```

#### 4. **Checking for Exposed Secrets**
```bash
# Search Git history for patterns
git log --all -S "AIza" --oneline
```

#### 5. **Environment Variables Checklist**
- [ ] `.env` is in `.gitignore`
- [ ] No secrets in code
- [ ] Railway environment variables set
- [ ] Streamlit Cloud secrets configured
- [ ] Local `.env` populated

## 🚨 Emergency Response

If a secret is exposed:
1. **Immediately revoke the key** (highest priority)
2. Generate new key
3. Update in all environments
4. Check logs for unauthorized usage
5. Consider security audit

## 📋 Current Protected Secrets
- `GEMINI_API_KEY`
- `BINANCE_API_KEY`
- `BINANCE_SECRET`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `DASHBOARD_PASSWORD`

**Remember: It only takes ONE mistake to compromise security!**
