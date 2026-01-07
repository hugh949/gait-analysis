#!/bin/bash
# Quick script to check if deployment script is running and Azure status

echo "🔍 Checking Script and Deployment Status"
echo "=========================================="
echo ""

# Check if fix-and-deploy-backend.sh is running
echo "📋 Step 1: Checking if deployment script is running..."
SCRIPT_PID=$(ps aux | grep -E "[f]ix-and-deploy-backend.sh" | awk '{print $2}' | head -1)

if [ -n "$SCRIPT_PID" ]; then
  echo "   ✅ Script IS running (PID: $SCRIPT_PID)"
  echo "   • Process details:"
  ps -p $SCRIPT_PID -o pid,etime,command 2>/dev/null || echo "   ⚠️  Process may have finished"
else
  echo "   ❌ Script is NOT running"
fi

echo ""
echo "📋 Step 2: Checking Azure App Service status..."
RESOURCE_GROUP="gait-analysis-rg-wus3"
APP_SERVICE_NAME="gait-analysis-api-simple"

APP_STATE=$(az webapp show \
  --name $APP_SERVICE_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "state" -o tsv 2>/dev/null || echo "unknown")

echo "   • App Service State: $APP_STATE"

echo ""
echo "📋 Step 3: Checking backend health..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
  https://$APP_SERVICE_NAME.azurewebsites.net/health 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
  echo "   ✅ Backend is responding! (HTTP $HTTP_CODE)"
elif [ "$HTTP_CODE" = "000" ]; then
  echo "   ⏳ Backend is not responding (may be building/starting)"
elif [ "$HTTP_CODE" = "503" ] || [ "$HTTP_CODE" = "502" ]; then
  echo "   ⏳ Backend is starting... (HTTP $HTTP_CODE - expected during build)"
else
  echo "   ⚠️  Backend returned: HTTP $HTTP_CODE"
fi

echo ""
echo "📋 Step 4: Recent deployment status..."
az webapp deployment list \
  --name $APP_SERVICE_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "[0].{Time:startTime,Status:status,Message:message}" \
  -o table 2>/dev/null || echo "   ⚠️  Could not fetch deployment status"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "💡 If script is hung:"
echo "   • Press Ctrl+C to stop it"
echo "   • Check Azure logs: az webapp log tail --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP"
echo "   • The build may still be running in Azure even if script appears hung"
echo "═══════════════════════════════════════════════════════════"
echo ""



