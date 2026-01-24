#!/bin/bash
# Fetch and filter Azure Log Stream logs for specific patterns
# Usage: ./fetch_azure_logs_filtered.sh [filter_pattern]
# Examples:
#   ./fetch_azure_logs_filtered.sh "STEP 3"
#   ./fetch_azure_logs_filtered.sh "STEP 4"
#   ./fetch_azure_logs_filtered.sh "ERROR\|❌"
#   ./fetch_azure_logs_filtered.sh "upload"

APP_NAME="gaitanalysisapp"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-gait-analysis-rg-wus3}"
LOG_LINES="${LOG_LINES:-500}"
FILTER="${1:-}"

echo "=========================================="
echo "Fetching Azure Log Stream logs..."
echo "App: $APP_NAME"
echo "Resource Group: $RESOURCE_GROUP"
if [ -n "$FILTER" ]; then
    echo "Filter: $FILTER"
fi
echo "=========================================="
echo ""

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo "❌ Error: Azure CLI is not installed"
    exit 1
fi

# Fetch logs
LOG_OUTPUT=$(az webapp log tail \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" 2>/dev/null | \
    tail -n "$LOG_LINES")

if [ -n "$FILTER" ]; then
    echo "$LOG_OUTPUT" | grep -i "$FILTER"
else
    echo "$LOG_OUTPUT"
fi

echo ""
echo "=========================================="
echo "Log fetch complete"
echo "=========================================="
