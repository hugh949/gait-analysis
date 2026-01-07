#!/bin/bash
# Helper script to set up GitHub Actions secrets
# This script helps you get the values needed for GitHub secrets

set -e

echo "🔐 GitHub Actions Secrets Setup Helper"
echo "======================================"
echo ""
echo "This script will help you get the values needed for GitHub secrets."
echo "You'll need to manually add these to GitHub:"
echo "  Repository → Settings → Secrets and variables → Actions"
echo ""

RESOURCE_GROUP="gait-analysis-rg-wus3"
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

echo "📋 Step 1: Create Azure Service Principal for GitHub Actions"
echo "------------------------------------------------------------"
echo ""
echo "Run this command to create a service principal:"
echo ""
echo "az ad sp create-for-rbac --name \"gait-analysis-github-actions\" \\"
echo "  --role contributor \\"
echo "  --scopes /subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP \\"
echo "  --sdk-auth"
echo ""
echo "Copy the ENTIRE JSON output and add it as a GitHub secret named:"
echo "  AZURE_CREDENTIALS"
echo ""

read -p "Press Enter after you've created the service principal..."

echo ""
echo "📋 Step 2: Get Static Web Apps Deployment Token"
echo "------------------------------------------------"
echo ""

STATIC_WEB_APP_NAME=$(az staticwebapp list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "")

if [ -n "$STATIC_WEB_APP_NAME" ]; then
    echo "Getting deployment token for: $STATIC_WEB_APP_NAME"
    echo ""
    
    # Try to get the token
    TOKEN=$(az staticwebapp secrets list \
        --name "$STATIC_WEB_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "properties.apiKey" -o tsv 2>/dev/null || echo "")
    
    if [ -n "$TOKEN" ] && [ "$TOKEN" != "null" ]; then
        echo "✅ Deployment Token:"
        echo "$TOKEN"
        echo ""
        echo "Add this as a GitHub secret named:"
        echo "  AZURE_STATIC_WEB_APPS_DEPLOYMENT_TOKEN"
    else
        echo "⚠️  Could not retrieve token automatically."
        echo ""
        echo "Get it manually from Azure Portal:"
        echo "  1. Go to Azure Portal"
        echo "  2. Navigate to your Static Web App"
        echo "  3. Settings → Deployment tokens"
        echo "  4. Copy the deployment token"
        echo ""
        echo "Add it as a GitHub secret named:"
        echo "  AZURE_STATIC_WEB_APPS_DEPLOYMENT_TOKEN"
    fi
else
    echo "⚠️  Static Web App not found in resource group."
    echo "   Get the deployment token manually from Azure Portal."
fi

echo ""
echo "📋 Step 3: SQL Database Password (if using SQL)"
echo "------------------------------------------------"
echo ""

SQL_SERVER=$(az sql server list --resource-group "$RESOURCE_GROUP" --query "[?contains(name, 'gait')].name" -o tsv | head -1)

if [ -n "$SQL_SERVER" ]; then
    echo "SQL Server found: $SQL_SERVER"
    echo ""
    echo "If you're using Azure SQL Database, add the password as:"
    echo "  AZURE_SQL_PASSWORD"
    echo ""
    echo "Note: The password was set when the SQL server was created."
    echo "      If you don't remember it, you may need to reset it."
else
    echo "No SQL server found. This secret is optional."
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ Setup Complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📝 Summary of GitHub Secrets to Add:"
echo ""
echo "1. AZURE_CREDENTIALS"
echo "   - Service principal JSON from Step 1"
echo ""
echo "2. AZURE_STATIC_WEB_APPS_DEPLOYMENT_TOKEN"
echo "   - Deployment token from Step 2"
echo ""
echo "3. AZURE_SQL_PASSWORD (optional)"
echo "   - SQL database password if using SQL"
echo ""
echo "🔗 Add secrets at:"
echo "   https://github.com/YOUR_USERNAME/YOUR_REPO/settings/secrets/actions"
echo ""
echo "📖 Full setup guide: .github/GITHUB_ACTIONS_SETUP.md"
echo ""


