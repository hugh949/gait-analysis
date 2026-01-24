#!/bin/bash
# Fetch Azure Log Stream logs for the Gait Analysis app
# This should be run BEFORE making any changes to understand current behavior

APP_NAME="gaitanalysisapp"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-gait-analysis-rg-wus3}"  # Default or from env
LOG_LINES="${LOG_LINES:-200}"  # Number of recent log lines to fetch

echo "=========================================="
echo "Fetching Azure Log Stream logs..."
echo "App: $APP_NAME"
echo "Resource Group: $RESOURCE_GROUP"
echo "Lines: $LOG_LINES"
echo "=========================================="
echo ""

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo "❌ Error: Azure CLI is not installed"
    echo "Install from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
    exit 1
fi

# Check if logged in
if ! az account show &> /dev/null; then
    echo "⚠️  Not logged into Azure. Attempting login..."
    az login
fi

# Fetch logs using Azure CLI
echo "📥 Fetching recent logs..."
az webapp log tail \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --output json 2>/dev/null | \
    tail -n "$LOG_LINES" | \
    jq -r '.message // . // empty' 2>/dev/null || \
    az webapp log tail \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" 2>/dev/null | \
        tail -n "$LOG_LINES"

echo ""
echo "=========================================="
echo "Log fetch complete"
echo "=========================================="
echo ""
echo "💡 Tips:"
echo "  - Filter for [STEP 3] or [STEP 4] to see specific step logs"
echo "  - Look for ❌ errors or ⚠️ warnings"
echo "  - Check for completion messages: ✅"
echo ""
