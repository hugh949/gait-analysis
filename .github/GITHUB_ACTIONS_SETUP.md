# GitHub Actions Deployment Setup Guide

This guide explains how to set up automated deployments to Azure using GitHub Actions.

## Overview

We have three GitHub Actions workflows:

1. **deploy-backend.yml** - Deploys backend only (when `backend/` changes)
2. **deploy-frontend.yml** - Deploys frontend only (when `frontend/` changes)
3. **deploy-integrated.yml** - Deploys both frontend and backend together (when both change)

## Required GitHub Secrets

You need to configure the following secrets in your GitHub repository:

### 1. AZURE_CREDENTIALS

This is a service principal JSON that allows GitHub Actions to authenticate with Azure.

**How to create:**

```bash
# Login to Azure
az login

# Create service principal (replace with your subscription ID)
az ad sp create-for-rbac --name "gait-analysis-github-actions" \
  --role contributor \
  --scopes /subscriptions/YOUR_SUBSCRIPTION_ID/resourceGroups/gait-analysis-rg-wus3 \
  --sdk-auth

# Copy the entire JSON output
```

**Add to GitHub:**
1. Go to your GitHub repository
2. Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Name: `AZURE_CREDENTIALS`
5. Value: Paste the entire JSON output from the command above

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

Workflows trigger automatically when you push to the `main` branch:

- **Backend changes** (`backend/**`) → Runs `deploy-backend.yml`
- **Frontend changes** (`frontend/**`) → Runs `deploy-frontend.yml`
- **Both change** → Runs `deploy-integrated.yml`

### Manual Deployment

You can also trigger deployments manually:

1. Go to your GitHub repository
2. Click "Actions" tab
3. Select the workflow you want to run
4. Click "Run workflow"
5. Select branch and click "Run workflow"

## Workflow Steps

### Backend Deployment (`deploy-backend.yml`)

1. Checkout code
2. Build Docker image in Azure Container Registry (ACR)
3. Configure App Service to use the new image
4. Set environment variables (CORS, ports, Azure service credentials)
5. Restart App Service
6. Wait for container to start
7. Run health check

### Frontend Deployment (`deploy-frontend.yml`)

1. Checkout code
2. Install Node.js dependencies
3. Build frontend
4. Deploy to Azure Static Web Apps

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


