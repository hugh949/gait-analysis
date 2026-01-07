# 🔄 How Automatic Deployment Works

## Understanding the Flow

### The Process

1. **You push code from Cursor** (using your GitHub Personal Access Token)
   - This happens in the Cursor terminal
   - You authenticate with your Personal Access Token
   - Code goes to GitHub

2. **GitHub Actions runs automatically** (on GitHub's servers, not in Cursor)
   - GitHub detects the push
   - GitHub Actions workflow runs automatically
   - Builds your frontend
   - Deploys to Azure Static Web App

3. **Deployment completes** (2-3 minutes)
   - Your changes are live on Azure
   - You can view deployment status in GitHub Actions

## Important Points

✅ **Cursor**: Where you push code (uses Personal Access Token)
✅ **GitHub**: Where automatic deployments run (uses Azure deployment token from Secrets)
❌ **Cursor does NOT run deployments** - GitHub Actions does

## Setup Steps

### Step 1: Push Code to GitHub (Use Personal Access Token)

You've already created the Personal Access Token! Now push your code:

**In Cursor Terminal** (`` Ctrl + ` ``):
```bash
cd /Users/hughrashid/Cursor/Gait-Analysis
git push -u origin main
```

**When prompted**:
- **Username**: `hugh949`
- **Password**: (paste your GitHub Personal Access Token)

### Step 2: Add Azure Deployment Token to GitHub Secrets

The Personal Access Token is for pushing code. You also need the Azure deployment token for GitHub Actions to deploy:

1. **Go to**: https://github.com/hugh949/gait-analysis/settings/secrets/actions

2. **Click**: "New repository secret"

3. **Fill in**:
   - **Name**: `AZURE_STATIC_WEB_APPS_API_TOKEN`
   - **Value**: `1aaad346d4e5bd36241348cfca7dde044f070ae22516f876ea34bde2d6f6bcd201-0ab6484a-20a7-49f6-979d-bd3285fc68d000f21100a467810f`

4. **Click**: "Add secret"

## After Setup

Once both are done:

1. **Push code** (any time, from Cursor):
   ```bash
   git add .
   git commit -m "Your changes"
   git push
   ```
   - Use Personal Access Token when prompted

2. **GitHub Actions automatically**:
   - Detects the push
   - Builds your frontend
   - Deploys to Azure
   - Takes 2-3 minutes

3. **View deployment**:
   - Go to: https://github.com/hugh949/gait-analysis/actions
   - See deployment status and logs

## Two Tokens, Two Purposes

| Token | Purpose | Where Used |
|-------|---------|------------|
| **GitHub Personal Access Token** | Push code to GitHub | Cursor terminal (git push) |
| **Azure Deployment Token** | Deploy to Azure | GitHub Secrets (for GitHub Actions) |

## Summary

✅ **You have**: GitHub Personal Access Token (for pushing)
⏳ **You need**: Push code to GitHub (use the token)
⏳ **You need**: Add Azure deployment token to GitHub Secrets
🚀 **After that**: Every push automatically deploys!

## Quick Links

- **Repository**: https://github.com/hugh949/gait-analysis
- **Secrets**: https://github.com/hugh949/gait-analysis/settings/secrets/actions
- **Actions**: https://github.com/hugh949/gait-analysis/actions
- **Frontend**: https://jolly-meadow-0a467810f.1.azurestaticapps.net



