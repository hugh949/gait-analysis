#!/bin/bash
# Quick status check script

echo "🔍 Checking Deployment and Backend Status"
echo "=========================================="
echo ""

RESOURCE_GROUP="gait-analysis-rg-wus3"
APP_SERVICE_NAME="gait-analysis-api-simple"

echo "📋 Deployment Status:"
az webapp deployment list \
  --name $APP_SERVICE_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "[0].{Time:startTime,Status:status,Message:message}" \
  -o table

echo ""
echo "🌐 Backend Health Check:"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
  https://$APP_SERVICE_NAME.azurewebsites.net/health 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
  echo "   ✅ Backend is healthy! (HTTP $HTTP_CODE)"
  echo ""
  echo "   Response:"
  curl -s https://$APP_SERVICE_NAME.azurewebsites.net/health | python3 -m json.tool 2>/dev/null || curl -s https://$APP_SERVICE_NAME.azurewebsites.net/health
elif [ "$HTTP_CODE" = "000" ]; then
  echo "   ⏳ Backend is not responding (may still be building/starting)"
  echo "   • This is normal if deployment just completed"
  echo "   • Oryx build takes 5-10 minutes for first deployment"
elif [ "$HTTP_CODE" = "503" ] || [ "$HTTP_CODE" = "502" ]; then
  echo "   ⏳ Backend is starting... (HTTP $HTTP_CODE)"
  echo "   • Service is initializing"
else
  echo "   ⚠️  Backend returned: HTTP $HTTP_CODE"
fi

echo ""
echo "📊 App Service State:"
az webapp show \
  --name $APP_SERVICE_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "{State:state,LastModified:lastModifiedTimeUtc}" \
  -o table

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "💡 Next Steps:"
echo "   • If HTTP 200: Backend is ready! ✅"
echo "   • If HTTP 000/503: Wait 5-10 minutes for build to complete"
echo "   • Check logs: az webapp log tail --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP"
echo "═══════════════════════════════════════════════════════════"
echo ""



