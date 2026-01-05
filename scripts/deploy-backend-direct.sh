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

echo "📦 Step 1/4: Building Docker image..."
az acr build --registry $REGISTRY --image $IMAGE .

if [ $? -ne 0 ]; then
  echo "❌ Build failed"
  exit 1
fi

echo "✅ Build complete"
echo ""

echo "🔧 Step 2/4: Updating App Service container..."
az webapp config container set \
  --name $APP_SERVICE_NAME \
  --resource-group $RESOURCE_GROUP \
  --docker-custom-image-name $REGISTRY.azurecr.io/$IMAGE

if [ $? -ne 0 ]; then
  echo "❌ Container update failed"
  exit 1
fi

echo "✅ Container updated"
echo ""

echo "🔄 Step 3/4: Restarting App Service..."
az webapp restart --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP

if [ $? -ne 0 ]; then
  echo "❌ Restart failed"
  exit 1
fi

echo "✅ App Service restarted"
echo ""

echo "⏳ Step 4/4: Waiting for app to start (30 seconds)..."
sleep 30

echo ""
echo "✅ Deployment complete!"
echo "🔗 Backend URL: https://$APP_SERVICE_NAME.azurewebsites.net"
echo ""

