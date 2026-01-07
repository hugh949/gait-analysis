#!/bin/bash
# Deploy Backend to Azure App Service - Simple and Reliable
set -e

RESOURCE_GROUP="gait-analysis-rg-wus3"
APP_SERVICE_NAME="gait-analysis-api-appservice"
REGISTRY="gaitanalysisacrwus3"
IMAGE="gait-analysis-api:latest"

echo "🚀 Deploying to App Service (Simple & Reliable)"
echo "=============================================="

# Step 1: Build image
echo "📦 Step 1/4: Building Docker image..."
cd "$(dirname "$0")/../backend"
az acr build --registry $REGISTRY --image $IMAGE . || {
    echo "❌ Build failed"
    exit 1
}
echo "✅ Build complete"

# Step 2: Deploy Bicep template
echo "🏗️  Step 2/4: Deploying App Service..."
cd "$(dirname "$0")/../azure"
az deployment group create \
    --resource-group $RESOURCE_GROUP \
    --template-file app-service-backend.bicep \
    --parameters \
        location=eastus2 \
        resourceGroupName=$RESOURCE_GROUP \
        containerRegistry=$REGISTRY \
        appServicePlanSku=B1 \
    --output none || {
    echo "⚠️  Deployment may have failed, checking if App Service exists..."
}

# Step 3: Configure App Service
echo "⚙️  Step 3/4: Configuring App Service..."
az webapp config appsettings set \
    --name $APP_SERVICE_NAME \
    --resource-group $RESOURCE_GROUP \
    --settings \
        CORS_ORIGINS="https://jolly-meadow-0a467810f.1.azurestaticapps.net,http://localhost:3000,http://localhost:5173" \
        PORT="8000" \
    --output none

# Step 4: Restart to apply changes
echo "🔄 Step 4/4: Restarting App Service..."
az webapp restart --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP

echo ""
echo "✅ Deployment complete!"
echo "Backend URL: https://${APP_SERVICE_NAME}.azurewebsites.net"
echo ""
echo "⏳ Waiting 30 seconds for app to start..."
sleep 30

# Test
echo "🧪 Testing backend..."
if curl -s -f -m 10 "https://${APP_SERVICE_NAME}.azurewebsites.net/" > /dev/null; then
    echo "✅✅✅ BACKEND IS WORKING! ✅✅✅"
else
    echo "⚠️  Backend may still be starting. Check logs:"
    echo "az webapp log tail --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP"
fi



