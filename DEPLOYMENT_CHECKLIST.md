# SRA Agent Streamlit App - Deployment Checklist

This checklist guides you through preparing and verifying the SRA Agent for production deployment on Streamlit Community Cloud.

---

## Pre-Deployment Verification

### ✅ Code Quality & Testing

- [ ] **All local tests pass**
  ```bash
  pytest tests/ -v
  ```
  **Expected**: 57 passed, 10 skipped (live API tests skip by default)

- [ ] **No debugging code in codebase**
  - No `print()` statements in production code
  - No commented-out code
  - No temporary test files

- [ ] **Git status is clean**
  ```bash
  git status
  ```
  **Expected**: Only committed changes, no untracked files (except those in .gitignore)

### ✅ Security & Secrets

- [ ] **All sensitive files in .gitignore**
  - `.env` files excluded
  - `.streamlit/secrets.toml` excluded
  - `*secrets.toml` pattern covers all variants
  - No API keys or credentials in repository

- [ ] **No hardcoded credentials in code**
  - No API keys in source files
  - No passwords in configuration
  - All credentials loaded from `st.secrets`

- [ ] **Password protection implemented**
  - `app.py` requires password at startup
  - Uses `hmac.compare_digest()` for secure comparison
  - Password configured in Streamlit secrets

### ✅ Configuration Files

- [ ] **`.streamlit/config.toml` exists and configured**
  - Theme settings defined
  - Server configuration set
  - Logger and client settings configured

- [ ] **`.streamlit/secrets.toml.template` exists**
  - Template shows required structure
  - Documents all required secrets:
    - `app_password`
    - `GEMINI_API_KEY`
    - `[gcp_service_account]` section

- [ ] **`requirements.txt` exists and up-to-date**
  - Contains all dependencies needed for Streamlit Cloud
  - Excludes development dependencies (pytest, etc.)
  - Version constraints specified

- [ ] **`.gitignore` includes deployment exclusions**
  - Secrets files excluded
  - Cache directories excluded
  - Result exports excluded

### ✅ Core Features Implemented

- [ ] **Agent Interface (Milestone 1)**
  - `create_sra_agent()` factory function available
  - `query_sra()` query interface working
  - Credential injection system in place

- [ ] **Authentication (Milestone 2)**
  - Password gate functioning
  - Secure password comparison implemented
  - Session state tracking works

- [ ] **Rate Limiting (Milestone 3)**
  - Rate limiter module created
  - Session-based limits enforced (10/session)
  - Hourly limits enforced (50/hour)
  - Cooldown periods working (30 seconds)

- [ ] **Chat UI (Milestone 4)**
  - Chat message display working
  - User input handling functional
  - Agent integration complete
  - Loading spinners show during processing

- [ ] **BigQuery Integration (Milestone 5)**
  - Service account credential loading implemented
  - BigQuery client injection working
  - Credentials from Streamlit secrets

- [ ] **Testing Suite (Milestone 6)**
  - All unit tests passing (param extraction, SQL, rate limiting)
  - Mock implementations functional
  - Cost tracking in place

- [ ] **Deployment Config (Milestone 7)**
  - `requirements.txt` created
  - `DEPLOYMENT.md` comprehensive
  - `.gitignore` updated

- [ ] **Error Handling (Milestone 8)**
  - Chat history trimming at 20 messages
  - Error recovery mechanisms in place
  - User-friendly error messages displayed
  - Progress indicators during processing

---

## Local Testing (Before Deployment)

### Test Password Protection

```bash
# 1. Start the app
streamlit run app.py

# 2. Try accessing without password
# Expected: Password prompt appears

# 3. Enter wrong password
# Expected: Error message "Incorrect password"

# 4. Enter correct password (from secrets file)
# Expected: Chat interface loads
```

### Test Rate Limiting

```bash
# After logging in:

# 1. Make a simple query
# Input: "Show me human data"
# Expected: Results appear, "1/10" shown in sidebar

# 2. Make 9 more queries (with at least 30 second delays)
# Expected: Counter increments to "10/10"

# 3. Try to make 11th query immediately
# Expected: Rate limit message: "You've hit the session limit..."

# 4. Wait 1 hour (or clear session for testing)
# Expected: Hourly counter resets, queries available again
```

### Test Core Functionality

```bash
# Query examples to test:
1. "Find human transcriptomic data"
   Expected: Parameters extracted, SQL generated, results returned

2. "Homo sapiens, genomic, Illumina platform"
   Expected: Structured query with multiple filters

3. "Mouse metagenomic samples with keywords gut microbiome"
   Expected: Parameter extraction with keyword search

4. Test error recovery (intentional)
   - Clear chat mid-query
   - Test multiple consecutive queries
   Expected: App handles gracefully, error messages clear
```

### Verify Sidebar Controls

- [ ] **Queries remaining counter** shows correct counts
- [ ] **Clear Chat** button resets conversation and thread ID
- [ ] **Download Results** button exports JSON of query results
- [ ] **Reset Agent** button appears and works if errors occur

---

## GCP Setup (Before Cloud Deployment)

### Service Account Creation

- [ ] **Create service account in GCP Console**
  ```
  Project: Your GCP Project
  Name: sra-agent-streamlit
  Roles:
    - BigQuery Data Editor (read/query data)
    - Generative AI User (use Gemini API)
  ```

- [ ] **Create and download JSON key**
  - Keep downloaded JSON file secure (don't commit!)
  - You'll paste this into Streamlit Cloud secrets

- [ ] **Enable required APIs**
  - [ ] BigQuery API
  - [ ] Generative AI API (for langchain-google-genai)
  - [ ] Cloud Resource Manager API

- [ ] **Configure billing budget alerts**
  - Set limit: $5-10/month
  - Alert threshold: 50% and 100%
  - Recipient email configured

---

## GitHub Preparation

- [ ] **All code committed and pushed to GitHub**
  ```bash
  git add .
  git commit -m "docs: finalize deployment documentation"
  git push origin main
  ```

- [ ] **Repository is public** (or shared with Streamlit)

- [ ] **Main branch is protected** (recommended)

- [ ] **`.gitignore` prevents secrets from being committed**
  ```bash
  # Verify no secrets in repo:
  git ls-files | grep -i secret
  git ls-files | grep -i .env
  # Should return nothing
  ```

---

## Streamlit Cloud Deployment

### Step 1: Connect Repository

- [ ] Log in to [Streamlit Cloud](https://share.streamlit.io)
- [ ] Click "New app" → Select your GitHub repository
- [ ] Configuration:
  ```
  Repository: your-org/langgraph-agent
  Branch: main
  Main file path: app.py
  ```
- [ ] Click "Deploy"

### Step 2: Configure Secrets

Once app is deployed:

- [ ] Click app settings → Secrets
- [ ] Copy secrets from `.streamlit/secrets.toml.template`
- [ ] Add:
  ```toml
  # Secure app password
  app_password = "your_secure_password_here"

  # Gemini API Key (from Google AI Studio)
  GEMINI_API_KEY = "your_gemini_api_key"

  # Service Account JSON (paste entire downloaded JSON)
  [gcp_service_account]
  type = "service_account"
  project_id = "your-project-id"
  private_key_id = "..."
  # ... full service account JSON ...
  ```

- [ ] Verify secrets saved successfully

### Step 3: Deploy & Test

- [ ] App rebuilds automatically after secrets saved
- [ ] Wait for "App is running" status
- [ ] Visit your app URL (provided by Streamlit Cloud)

---

## Production Verification Checklist

### Security

- [ ] [ ] Password protection works (can't access without password)
- [ ] [ ] Secrets not visible in app logs
- [ ] [ ] No error messages leak sensitive information
- [ ] [ ] Rate limiting prevents abuse

### Functionality

- [ ] [ ] Simple query works: "Show human data"
- [ ] [ ] Parameter extraction working
- [ ] [ ] BigQuery results returning correctly
- [ ] [ ] Chat history displays properly
- [ ] [ ] Sidebar controls functional
- [ ] [ ] Download results produces valid JSON

### Cost Control

- [ ] [ ] Rate limiting active (10 queries/session, 50/hour)
- [ ] [ ] Cooldown between queries enforced (30 seconds)
- [ ] [ ] GCP billing alerts configured and tested
- [ ] [ ] First test query costs ~$0.00-0.01

### Error Handling

- [ ] [ ] Graceful error messages for invalid queries
- [ ] [ ] Recovery from transient failures
- [ ] [ ] No stack traces in user interface
- [ ] [ ] Chat history auto-trim at 20 messages

### Monitoring

- [ ] [ ] Streamlit Cloud dashboard logs accessible
- [ ] [ ] GCP billing dashboard shows usage
- [ ] [ ] Cost tracking within expected limits
- [ ] [ ] No unexpected API calls

---

## Post-Deployment Monitoring

### Daily (First Week)

- [ ] Check Streamlit Cloud logs for errors
- [ ] Verify GCP billing dashboard (no unexpected charges)
- [ ] Test app functionality
- [ ] Monitor rate limiting effectiveness

### Weekly

- [ ] Review cost trends in GCP billing
- [ ] Check error logs for patterns
- [ ] Verify all features still working
- [ ] Confirm password protection active

### Monthly

- [ ] Analyze usage patterns
- [ ] Adjust rate limits if needed
- [ ] Review and optimize costs
- [ ] Plan for feature updates

---

## Rollback Plan (If Issues Arise)

### Quick Fix (Code Issue)
```bash
# 1. Fix code locally
# 2. Test thoroughly
# 3. Push to GitHub
# 4. Streamlit Cloud auto-redeployes

git add .
git commit -m "fix: issue description"
git push origin main
# Wait 2-3 minutes for auto-deploy
```

### Secrets Issue
- [ ] Check Streamlit Cloud dashboard → Secrets
- [ ] Verify all required fields present
- [ ] Check for JSON formatting errors
- [ ] Re-save secrets to trigger reload

### Credentials Issue
- [ ] Verify GCP service account has correct roles
- [ ] Download new JSON key if old one deleted
- [ ] Update secrets in Streamlit Cloud dashboard
- [ ] Test BigQuery query to verify connection

### Complete Rollback
```bash
# Revert to known-good commit
git revert <commit-hash>
git push origin main
# Streamlit Cloud auto-redeploysmm
```

---

## Support & Troubleshooting

### Common Issues & Fixes

| Issue | Cause | Solution |
|-------|-------|----------|
| "Failed to load credentials" | Secrets not configured | Check Streamlit Cloud dashboard secrets |
| "BigQuery permission denied" | Service account lacks roles | Add BigQuery Data Editor role in GCP |
| "Rate limit exceeded" | Too many queries | Wait 30 seconds (cooldown) or clear chat |
| "No results found" | Query too restrictive | Ask agent to clarify search criteria |
| "Blank page" | Authentication issue | Check browser console for errors |
| "Password not working" | Secrets not loaded | Verify `app_password` in Streamlit Cloud |

### Debug Mode (Local Only)

```bash
# Enable debug logging
STREAMLIT_LOGGER_LEVEL=debug streamlit run app.py

# Check logs for detailed errors
tail -f /tmp/streamlit_debug.log
```

### Contact & Resources

- **Streamlit Docs**: https://docs.streamlit.io
- **Deployment Guide**: See `DEPLOYMENT.md`
- **Issues**: GitHub Issues in repository
- **GCP Docs**: https://cloud.google.com/docs

---

## Sign-Off

**Deployment Checklist Version**: 1.0
**Created**: 2026-01-22
**Last Updated**: 2026-01-22

**Deployed By**: ________________
**Date**: ________________
**Notes**: _______________________________________________

---

✅ **Ready for Production!**

Once you've completed all checkboxes above, your SRA Agent is ready for production deployment on Streamlit Community Cloud.
