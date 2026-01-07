# GitHub Actions Deployment Setup Guide

This guide explains how to set up automated deployments to Azure using GitHub Actions.

## Overview

We have one GitHub Actions workflow:

1. **deploy-integrated.yml** - Deploys the integrated application (frontend + backend in one Docker container)

This is the correct workflow for our current architecture where the frontend and backend are integrated into a single application served from one App Service.

## Required GitHub Secrets

You need to configure the following secrets in your GitHub repository:

### 1. AZURE_CREDENTIALS

This is a service principal JSON that allows GitHub Actions to authenticate with Azure.

**Required JSON format:**
```json
{
  "clientId": "...",
  "clientSecret": "...",
  "subscriptionId": "...",
  "tenantId": "..."
}
```

**How to create (Easiest method):**

```bash
# Run the helper script
cd scripts
./create-azure-service-principal.sh

# The script will output the JSON - copy it entirely
```

**Or create manually:**

```bash
# Login to Azure
az login

# Create service principal (replace with your subscription ID)
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
az ad sp create-for-rbac --name "gait-analysis-github-actions" \
  --role contributor \
  --scopes /subscriptions/$SUBSCRIPTION_ID/resourceGroups/gait-analysis-rg-wus3 \
  --sdk-auth

# Copy the ENTIRE JSON output (must include all 4 fields)
```

**Add to GitHub:**
1. Go to: https://github.com/hugh949/Gait-Analysis/settings/secrets/actions
2. Click "New repository secret"
3. Name: `AZURE_CREDENTIALS` (exact name, case-sensitive)
4. Value: Paste the **ENTIRE** JSON output (must be valid JSON)
5. Click "Add secret"

**⚠️ Important:**
- The JSON must include all 4 fields: `clientId`, `clientSecret`, `subscriptionId`, `tenantId`
- Copy the ENTIRE JSON output, including the curly braces `{ }`
- Make sure there are no extra characters or line breaks
- The secret name must be exactly `AZURE_CREDENTIALS` (case-sensitive)

### 2. AZURE_STATIC_WEB_APPS_DEPLOYMENT_TOKEN

This is the deployment token for Azure Static Web Apps.

**How to get:**

```bash
# Get the deployment token from Azure Portal or CLI
az staticwebapp secrets list \
  --name gentle-sky-0a498ab1e \
  --resource-group gait-analysis-rg-wus3 \
  --query properties.apiKey -o tsv
```

**Or from Azure Portal:**
1. Go to Azure Portal
2. Navigate to your Static Web App
3. Settings → Deployment tokens
4. Copy the deployment token

**Add to GitHub:**
1. Go to your GitHub repository
2. Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Name: `AZURE_STATIC_WEB_APPS_DEPLOYMENT_TOKEN`
5. Value: Paste the deployment token

### 3. AZURE_SQL_PASSWORD (Optional)

If you're using Azure SQL Database, add the SQL password as a secret.

**Add to GitHub:**
1. Go to your GitHub repository
2. Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Name: `AZURE_SQL_PASSWORD`
5. Value: Your SQL database password

## Azure Resources

The workflows use these Azure resources (already created):

- **Resource Group**: `gait-analysis-rg-wus3`
- **App Service**: `gaitanalysisapp`
- **Container Registry**: `gaitacr737`
- **Static Web App**: `gentle-sky-0a498ab1e` (URL: https://gentle-sky-0a498ab1e.4.azurestaticapps.net)

## How It Works

### Automatic Deployment

The workflow triggers automatically when you push to the `main` branch and any of these paths change:

- **Backend changes** (`backend/**`)
- **Frontend changes** (`frontend/**`)
- **Workflow changes** (`.github/workflows/deploy-integrated.yml`)
- **Deployment script changes** (`scripts/deploy-integrated-app.sh`)

### Manual Deployment

You can also trigger deployments manually:

1. Go to your GitHub repository
2. Click "Actions" tab
3. Select the workflow you want to run
4. Click "Run workflow"
5. Select branch and click "Run workflow"

## Workflow Steps

### Integrated Deployment (`deploy-integrated.yml`)

1. Checkout code
2. Build frontend
3. Copy frontend build to backend directory
4. Build Docker image (includes frontend)
5. Configure App Service
6. Restart and health check

## Monitoring Deployments

### View Workflow Runs

1. Go to your GitHub repository
2. Click "Actions" tab
3. See all workflow runs and their status

### View Logs

1. Click on a workflow run
2. Click on a job
3. Expand steps to see detailed logs

### Azure Portal

- **App Service Logs**: Azure Portal → App Service → Log stream
- **Container Logs**: Azure Portal → App Service → Container settings → Logs

## Troubleshooting

### Workflow Fails

1. Check workflow logs in GitHub Actions
2. Check Azure Portal logs
3. Verify all secrets are set correctly
4. Verify Azure resources exist and are accessible

### Container Not Starting

1. Check ACR authentication (password should be set)
2. Check `WEBSITES_PORT=8000` is set
3. Check container logs in Azure Portal
4. Verify Docker image was built successfully

### Frontend Not Updating

1. Check Static Web Apps deployment token is correct
2. Check build logs in GitHub Actions
3. Clear browser cache
4. Check Static Web Apps logs in Azure Portal

## Best Practices

1. **Always test locally** before pushing to main
2. **Review workflow logs** after each deployment
3. **Use workflow_dispatch** for manual deployments when needed
4. **Monitor Azure costs** - GitHub Actions and Azure resources both incur costs
5. **Keep secrets secure** - Never commit secrets to the repository

## Next Steps

1. Set up the required GitHub secrets (see above)
2. Push your code to the `main` branch
3. Watch the GitHub Actions tab for deployment progress
4. Test your application after deployment completes


