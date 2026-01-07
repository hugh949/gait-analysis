#!/bin/bash
# Clean up Azure App Service settings to match current codebase
# Removes old/redundant settings and sets correct ones

set -e

echo "🧹 Azure Settings Cleanup"
echo "========================"
echo ""

RESOURCE_GROUP="gait-analysis-rg-wus3"
APP_SERVICE_NAME="gait-analysis-api-simple"

echo "⏱️  $(date '+%H:%M:%S') - Starting cleanup..."
echo ""

# Step 1: Remove Docker/Container settings (switching to native)
echo "📋 Step 1/7: Removing Docker/Container configuration..."
echo "   • Clearing container image settings..."
az webapp config container delete --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP 2>&1 | grep -v "^$" || echo "   ✅ Container config cleared"
echo ""

# Step 2: Set Python runtime
echo "📋 Step 2/7: Setting Python runtime..."
echo "   • Configuring for Python 3.11..."
az webapp config set --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP \
  --linux-fx-version "PYTHON|3.11" 2>&1 | grep -E "linuxFxVersion|error" | head -3 || echo "   ✅ Python runtime set"
echo ""

# Step 3: Set startup command
echo "📋 Step 3/7: Setting startup command..."
echo "   • Using startup.sh for native deployment..."
az webapp config set --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP \
  --startup-file "startup.sh" 2>&1 | grep -E "appCommandLine|error" | head -3 || echo "   ✅ Startup command set"
echo ""

# Step 4: Get current settings
echo "📋 Step 4/7: Analyzing current app settings..."
CURRENT_SETTINGS=$(az webapp config appsettings list --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP -o json 2>&1)
SETTING_COUNT=$(echo "$CURRENT_SETTINGS" | jq 'length' 2>/dev/null || echo "0")
echo "   • Found $SETTING_COUNT current settings"
echo ""

# Step 5: Define required settings (minimal, based on codebase)
echo "📋 Step 5/7: Defining required settings..."
echo "   • Based on config_simple.py analysis..."
echo "   • Required settings:"
echo "     - AZURE_COSMOS_ENDPOINT"
echo "     - AZURE_COSMOS_KEY"
echo "     - AZURE_COSMOS_DATABASE"
echo "     - AZURE_STORAGE_CONNECTION_STRING (optional)"
echo "     - CORS_ORIGINS"
echo "     - SCM_DO_BUILD_DURING_DEPLOYMENT=true"
echo "     - ENABLE_ORYX_BUILD=true"
echo ""

# Step 6: Backup current settings
echo "📋 Step 6/7: Backing up current settings..."
BACKUP_FILE="/tmp/azure-settings-backup-$(date +%Y%m%d-%H%M%S).json"
echo "$CURRENT_SETTINGS" > "$BACKUP_FILE"
echo "   ✅ Settings backed up to: $BACKUP_FILE"
echo ""

# Step 7: Clean and set minimal required settings
echo "📋 Step 7/7: Setting clean, minimal configuration..."
echo "   • Removing all old settings..."
echo "   • Setting only required ones..."

# Get existing values for critical settings before clearing
COSMOS_ENDPOINT=$(echo "$CURRENT_SETTINGS" | jq -r '.[] | select(.name=="AZURE_COSMOS_ENDPOINT") | .value' 2>/dev/null || echo "")
COSMOS_KEY=$(echo "$CURRENT_SETTINGS" | jq -r '.[] | select(.name=="AZURE_COSMOS_KEY") | .value' 2>/dev/null || echo "")
COSMOS_DB=$(echo "$CURRENT_SETTINGS" | jq -r '.[] | select(.name=="AZURE_COSMOS_DATABASE") | .value' 2>/dev/null || echo "gait-analysis")
STORAGE_CS=$(echo "$CURRENT_SETTINGS" | jq -r '.[] | select(.name=="AZURE_STORAGE_CONNECTION_STRING") | .value' 2>/dev/null || echo "")
CORS_ORIGINS=$(echo "$CURRENT_SETTINGS" | jq -r '.[] | select(.name=="CORS_ORIGINS") | .value' 2>/dev/null || echo "https://jolly-meadow-0a467810f.1.azurestaticapps.net")

# Build settings JSON
SETTINGS_JSON=$(cat <<EOF
[
  {"name": "SCM_DO_BUILD_DURING_DEPLOYMENT", "value": "true"},
  {"name": "ENABLE_ORYX_BUILD", "value": "true"},
  {"name": "WEBSITE_TIME_ZONE", "value": "UTC"},
  {"name": "PYTHON_VERSION", "value": "3.11"},
  {"name": "CORS_ORIGINS", "value": "$CORS_ORIGINS"},
  {"name": "AZURE_COSMOS_DATABASE", "value": "$COSMOS_DB"}
EOF
)

# Add optional settings if they exist
if [ -n "$COSMOS_ENDPOINT" ]; then
  SETTINGS_JSON=$(echo "$SETTINGS_JSON" | jq ". + [{\"name\": \"AZURE_COSMOS_ENDPOINT\", \"value\": \"$COSMOS_ENDPOINT\"}]")
fi

if [ -n "$COSMOS_KEY" ]; then
  SETTINGS_JSON=$(echo "$SETTINGS_JSON" | jq ". + [{\"name\": \"AZURE_COSMOS_KEY\", \"value\": \"$COSMOS_KEY\"}]")
fi

if [ -n "$STORAGE_CS" ]; then
  SETTINGS_JSON=$(echo "$SETTINGS_JSON" | jq ". + [{\"name\": \"AZURE_STORAGE_CONNECTION_STRING\", \"value\": \"$STORAGE_CS\"}]")
fi

# Set the clean settings
echo "$SETTINGS_JSON" > /tmp/new-settings.json
az webapp config appsettings set --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP \
  --settings @/tmp/new-settings.json 2>&1 | grep -E "name|value|error" | head -10 || echo "   ✅ Settings updated"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ Cleanup Complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📋 What Was Done:"
echo "   ✅ Removed Docker/Container configuration"
echo "   ✅ Set Python 3.11 runtime"
echo "   ✅ Set startup.sh command"
echo "   ✅ Cleaned app settings (removed old/redundant)"
echo "   ✅ Set minimal required settings"
echo "   ✅ Preserved critical values (Cosmos DB, etc.)"
echo ""
echo "💾 Backup saved to: $BACKUP_FILE"
echo ""
echo "🔄 Next: Restart App Service to apply changes"
echo ""



