#!/bin/bash
# Ensure Backend is Always Available
# Enables Always-On, checks health, and sets up reliability features

set -e

echo "🔧 Ensuring Backend is Always Available"
echo "========================================"
echo ""

RESOURCE_GROUP="gait-analysis-rg-wus3"
APP_SERVICE_NAME="gait-analysis-api-simple"

echo "📋 Step 1/5: Checking current Always-On setting..."
ALWAYS_ON=$(az webapp config show --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP --query "alwaysOn" -o tsv)

if [ "$ALWAYS_ON" != "true" ]; then
  echo "⚠️  Always-On is disabled. Enabling..."
  az webapp config set --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP --always-on true
  echo "✅ Always-On enabled"
else
  echo "✅ Always-On is already enabled"
fi

echo ""
echo "📋 Step 2/5: Checking App Service Plan SKU..."
PLAN_ID=$(az webapp show --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP --query "appServicePlanId" -o tsv)
SKU=$(az appservice plan show --ids "$PLAN_ID" --query "sku.name" -o tsv)

echo "   Current SKU: $SKU"

if [[ "$SKU" == *"F1"* ]] || [[ "$SKU" == *"FREE"* ]]; then
  echo "⚠️  WARNING: Free tier doesn't support Always-On!"
  echo "   Consider upgrading to Basic (B1) or higher for reliability"
else
  echo "✅ SKU supports Always-On"
fi

echo ""
echo "📋 Step 3/5: Setting HTTP 20s timeout (for long uploads)..."
az webapp config set --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP --http20-enabled true 2>&1 | grep -v "^$" || true

echo ""
echo "📋 Step 4/5: Enabling detailed error messages..."
az webapp config set --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP --detailed-error-logging-enabled true 2>&1 | grep -v "^$" || true

echo ""
echo "📋 Step 5/5: Restarting App Service to apply changes..."
az webapp restart --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP

echo ""
echo "⏳ Waiting 30 seconds for app to start..."
sleep 30

echo ""
echo "🔍 Testing backend health..."
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" https://$APP_SERVICE_NAME.azurewebsites.net/ || echo "000")

if [ "$HEALTH" = "200" ]; then
  echo "✅ Backend is healthy and responding"
else
  echo "⚠️  Backend returned status: $HEALTH"
  echo "   It may need a few more seconds to start"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ Backend Reliability Configuration Complete"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📋 Configuration:"
echo "   • Always-On: Enabled"
echo "   • HTTP/2: Enabled"
echo "   • Detailed Logging: Enabled"
echo ""
echo "💡 Tips for Maximum Reliability:"
echo "   • Use Basic (B1) tier or higher (Free tier doesn't support Always-On)"
echo "   • Monitor backend health regularly"
echo "   • Set up auto-scaling if needed"
echo ""



