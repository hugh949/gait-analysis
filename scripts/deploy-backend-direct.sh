#!/bin/bash
# Direct Backend Deployment from Cursor to Azure
# Bypasses GitHub - deploys local code directly to Azure App Service

set -e

echo "🚀 Direct Backend Deployment to Azure"
echo "======================================"
echo ""

RESOURCE_GROUP="gait-analysis-rg-eus2"
APP_SERVICE_NAME="gait-analysis-api-simple"
REGISTRY="gaitanalysisacreus2"
IMAGE="gait-analysis-api:latest"

# Navigate to backend directory
cd "$(dirname "$0")/../backend"

echo "📋 Deployment Configuration:"
echo "   • Resource Group: $RESOURCE_GROUP"
echo "   • App Service: $APP_SERVICE_NAME"
echo "   • Registry: $REGISTRY"
echo "   • Image: $IMAGE"
echo ""

echo "═══════════════════════════════════════════════════════════"
echo "📦 Step 1/4: Building Docker Image (Optimized)"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "⏳ Starting Docker build in Azure Container Registry..."
echo "   Using optimized Dockerfile for better caching..."
echo "   First build: 5-10 minutes (downloads dependencies)"
echo "   Subsequent builds: 1-2 minutes (uses cached layers)"
echo ""

# Build with optimized Dockerfile for better caching
BUILD_OUTPUT=$(az acr build --registry $REGISTRY --image $IMAGE --file Dockerfile.optimized . 2>&1)

if [ $? -ne 0 ]; then
  echo ""
  echo "❌ Build failed!"
  echo "$BUILD_OUTPUT" | tail -20
  exit 1
fi

# Extract build info
BUILD_ID=$(echo "$BUILD_OUTPUT" | grep -i "run id" | tail -1 | awk '{print $NF}' || echo "unknown")
BUILD_TIME=$(echo "$BUILD_OUTPUT" | grep -i "successful after" | tail -1 || echo "")

echo ""
echo "✅ Build complete!"
if [ -n "$BUILD_ID" ]; then
  echo "   • Build ID: $BUILD_ID"
fi
if [ -n "$BUILD_TIME" ]; then
  echo "   • $BUILD_TIME"
fi
echo ""

echo "═══════════════════════════════════════════════════════════"
echo "🔧 Step 2/4: Updating App Service Container"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "⏳ Updating container configuration..."
echo "   • Image: $REGISTRY.azurecr.io/$IMAGE"
echo ""

CONTAINER_OUTPUT=$(az webapp config container set \
  --name $APP_SERVICE_NAME \
  --resource-group $RESOURCE_GROUP \
  --container-image-name $REGISTRY.azurecr.io/$IMAGE 2>&1)

if [ $? -ne 0 ]; then
  echo ""
  echo "❌ Container update failed!"
  echo "$CONTAINER_OUTPUT" | tail -20
  exit 1
fi

echo "✅ Container configuration updated"
echo "   • New image will be pulled on next restart"
echo ""

echo "═══════════════════════════════════════════════════════════"
echo "🔄 Step 3/4: Restarting App Service"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "⏳ Restarting App Service to apply new container..."
echo "   • This will pull the new Docker image"
echo "   • Application will restart with new code"
echo ""

RESTART_OUTPUT=$(az webapp restart --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP 2>&1)

if [ $? -ne 0 ]; then
  echo ""
  echo "❌ Restart failed!"
  echo "$RESTART_OUTPUT"
  exit 1
fi

echo "✅ App Service restart initiated"
echo ""

echo "═══════════════════════════════════════════════════════════"
echo "⏳ Step 4/4: Waiting for Application to Start"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "⏳ Waiting for application to become ready..."
echo "   • Container is starting..."
echo "   • Application is initializing..."
echo ""

# Wait with progress updates
for i in {1..6}; do
  sleep 10
  echo "   ⏱️  Waited ${i}0 seconds... ($(($i * 10))/60)"
  
  # Try health check
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" https://$APP_SERVICE_NAME.azurewebsites.net/ 2>/dev/null || echo "000")
  
  if [ "$HTTP_CODE" = "200" ]; then
    echo ""
    echo "✅ Application is responding! (HTTP $HTTP_CODE)"
    break
  elif [ "$HTTP_CODE" != "000" ] && [ "$HTTP_CODE" != "503" ]; then
    echo "   ⚠️  Application returned HTTP $HTTP_CODE (may still be starting)"
  fi
done

echo ""
echo "🔍 Final health check..."
FINAL_CODE=$(curl -s -o /dev/null -w "%{http_code}" https://$APP_SERVICE_NAME.azurewebsites.net/ 2>/dev/null || echo "000")

if [ "$FINAL_CODE" = "200" ]; then
  echo "✅ Application is healthy and responding!"
elif [ "$FINAL_CODE" = "503" ]; then
  echo "⚠️  Application is still starting (HTTP 503)"
  echo "   • This is normal - it may take 1-2 more minutes"
  echo "   • The container is pulling the image and initializing"
elif [ "$FINAL_CODE" != "000" ]; then
  echo "⚠️  Application returned HTTP $FINAL_CODE"
  echo "   • Check logs if issues persist"
else
  echo "⚠️  Could not reach application"
  echo "   • Network issue or application still starting"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ Deployment Process Complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "🔗 Backend URL: https://$APP_SERVICE_NAME.azurewebsites.net"
echo "📊 Health Check: https://$APP_SERVICE_NAME.azurewebsites.net/"
echo ""
echo "💡 Next Steps:"
echo "   • Test the backend: curl https://$APP_SERVICE_NAME.azurewebsites.net/"
echo "   • View logs: az webapp log tail --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP"
echo "   • If still not responding, wait 1-2 more minutes and check again"
echo ""

