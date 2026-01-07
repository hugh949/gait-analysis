#!/bin/bash
# Quick script to check if deployment succeeded

RESOURCE_GROUP="gait-analysis-rg-wus3"
APP_SERVICE_NAME="gait-analysis-api-simple"

echo "🔍 Checking Deployment Status"
echo "============================="
echo ""

echo "📋 Recent Deployments:"
az webapp deployment list \
  --name $APP_SERVICE_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "[0:3].{Time:startTime,Status:status,Message:message,Active:active}" \
  -o table

echo ""
echo "🌐 Testing Backend Health:"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
  https://$APP_SERVICE_NAME.azurewebsites.net/health 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
  echo "   ✅ Backend is responding! (HTTP $HTTP_CODE)"
elif [ "$HTTP_CODE" = "000" ]; then
  echo "   ❌ Backend is not reachable (network error or not started)"
else
  echo "   ⚠️  Backend returned: HTTP $HTTP_CODE"
fi

echo ""
echo "📦 App Service Status:"
az webapp show \
  --name $APP_SERVICE_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "{State:state,DefaultHostName:defaultHostName,LastModified:lastModifiedTimeUtc}" \
  -o table

echo ""
echo "🔧 Startup Command:"
az webapp config show \
  --name $APP_SERVICE_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "appCommandLine" \
  -o tsv

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "📊 Summary:"
echo "   • If deployment shows 'Succeeded' or 'Active', upload worked"
echo "   • If backend returns HTTP 200, app is running"
echo "   • If command is still hanging, you can safely stop it (Ctrl+C)"
echo "═══════════════════════════════════════════════════════════"
echo ""



