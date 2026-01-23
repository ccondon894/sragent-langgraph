# Deployment Guide: SRA Agent Streamlit App

This guide walks through deploying the SRA Agent to Streamlit Community Cloud.

## Prerequisites

- GitHub account with the langgraph-agent repository
- Streamlit Community Cloud account (free at https://streamlit.io/cloud)
- Google Cloud Project with:
  - BigQuery API enabled
  - Generative AI API enabled (for Google Gemini)
  - Service Account with appropriate permissions

## Step 1: Prepare GCP Service Account

1. **Create a service account in Google Cloud Console**:
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Navigate to IAM & Admin → Service Accounts
   - Click "Create Service Account"
   - Name: `sra-agent-streamlit`
   - Grant these roles:
     - `BigQuery Data Editor` (for querying)
     - `Generative AI User` (for Gemini API)

2. **Create and download JSON key**:
   - Open the service account
   - Go to Keys → Add Key → Create new key
   - Select JSON format
   - Download the file (keep it secure!)

3. **Enable APIs** in your GCP project:
   - BigQuery API
   - Generative AI API (required for langchain-google-genai)

## Step 2: Deploy to Streamlit Community Cloud

1. **Push code to GitHub**:
   ```bash
   git add .
   git commit -m "chore: add deployment configuration"
   git push origin main
   ```

2. **Connect to Streamlit Cloud**:
   - Go to [Streamlit Cloud Dashboard](https://share.streamlit.io)
   - Click "New app"
   - Select your GitHub repository
   - Set main file path: `app.py`
   - Click "Deploy"

3. **Configure Secrets** in Streamlit Cloud Dashboard:
   - Click your app → Settings → Secrets
   - Add the following secrets (copy from `.streamlit/secrets.toml.template`):

   ```toml
   # Password for app access
   app_password = "your_secure_password_here"

   # Google Gemini API Key (optional if using service account)
   GEMINI_API_KEY = "your_gemini_api_key"

   # GCP Service Account (from downloaded JSON file)
   [gcp_service_account]
   type = "service_account"
   project_id = "your-project-id"
   private_key_id = "..."
   private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
   client_email = "sra-agent-streamlit@your-project-id.iam.gserviceaccount.com"
   client_id = "..."
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
   auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
   client_x509_cert_url = "..."
   ```

   **Important**: Paste the entire JSON service account file content into the `[gcp_service_account]` section, converting the `private_key` to a TOML-compatible format (replace newlines with `\n`).

## Step 3: Set Up Cost Controls in GCP

1. **Create a billing budget alert**:
   - Go to Billing → Budgets and alerts
   - Create a budget with a limit (e.g., $5/month)
   - Set alert threshold to 50% and 100%

2. **Monitor usage** (free tier provides):
   - BigQuery: 1TB free per month
   - Gemini API: Generous free tier for testing

3. **Track app usage**:
   - Check Streamlit Cloud dashboard for logs
   - Monitor GCP Billing Dashboard for actual costs

## Step 4: Verify Deployment

1. **Test password protection**:
   - Visit your Streamlit app URL
   - Verify password gate appears

2. **Test a simple query**:
   - After login, try: "Show me human data"
   - Verify results appear

3. **Test rate limiting**:
   - Make 10 consecutive queries (within cooldown)
   - Verify 11th query is blocked
   - Check "Queries remaining" counter in sidebar

4. **Check logs**:
   - Streamlit Cloud dashboard shows real-time logs
   - Check for credential or API errors

## Step 5: Local Development

To test locally before deployment:

```bash
# Install dependencies
poetry install

# Create local secrets file
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with your actual credentials

# Run app locally
streamlit run app.py
```

## Troubleshooting

### Issue: "Failed to load credentials"
- **Cause**: Secrets not configured in Streamlit Cloud
- **Fix**: Double-check `[gcp_service_account]` section in secrets

### Issue: "BigQuery permission denied"
- **Cause**: Service account missing required roles
- **Fix**: Grant `BigQuery Data Editor` and `Generative AI User` roles in GCP

### Issue: "Rate limit exceeded"
- **Cause**: Too many queries in short time
- **Fix**: Wait for cooldown period or clear chat history

### Issue: "No results found"
- **Cause**: Query parameters too restrictive
- **Fix**: Ask agent to clarify or broaden search criteria

## Cost Management

**Estimated monthly costs** (with typical usage):
- BigQuery: $0-5 (1TB free, $6.25/TB after)
- Gemini API: $0-2 (generous free tier)
- Streamlit Cloud: Free (community tier)

**To reduce costs**:
1. Use rate limiting (already implemented)
2. Cache BigQuery schema (already done in agent)
3. Keep prompt instructions concise
4. Set a daily GCP budget limit

## Next Steps

- Monitor app usage for 1-2 weeks
- Adjust rate limits if needed
- Add monitoring/alerting for errors
- Consider upgrading to Streamlit Team if more users needed

---

For issues or questions, check the main README.md or GitHub Issues.
