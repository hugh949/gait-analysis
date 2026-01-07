#!/bin/bash
# Deploy backend using Docker (no Oryx!)
# Build locally, push to ACR, deploy to App Service

set -e

RESOURCE_GROUP="gait-analysis-rg-wus3"
APP_SERVICE_NAME="gait-native-api-wus3"
REGISTRY="gaitnativeacr$(date +%s | tail -c 4)"
IMAGE_NAME="gait-analysis-native"
IMAGE_TAG="latest"

echo "🚀 Deploying Backend with Docker (No Oryx!)"
echo "=============================================="
echo ""
echo "This approach:"
echo "  ✅ Builds Docker image locally (you see progress)"
echo "  ✅ Pushes to Azure Container Registry"
echo "  ✅ Deploys pre-built container (no Oryx!)"
echo "  ✅ Much faster and more reliable"
echo ""

# Step 1: Create ACR if it doesn't exist
echo "📦 Step 1/5: Creating Azure Container Registry..."
if ! az acr show --name "$REGISTRY" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
    az acr create \
        --name "$REGISTRY" \
        --resource-group "$RESOURCE_GROUP" \
        --sku Basic \
        --admin-enabled true \
        > /dev/null 2>&1
    echo "✅ ACR created: $REGISTRY"
else
    echo "✅ ACR already exists: $REGISTRY"
fi

# Step 2: Get ACR credentials
echo ""
echo "🔐 Step 2/5: Getting ACR credentials..."
ACR_USERNAME=$(az acr credential show --name "$REGISTRY" --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name "$REGISTRY" --query passwords[0].value -o tsv)
ACR_LOGIN_SERVER=$(az acr show --name "$REGISTRY" --query loginServer -o tsv)

echo "✅ ACR Login Server: $ACR_LOGIN_SERVER"

# Step 3: Build Docker image locally
echo ""
echo "🔨 Step 3/5: Building Docker image locally..."
echo "   This gives you full control and visibility!"
cd backend

docker build \
    -f Dockerfile.azure-native \
    -t "$ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG" \
    . 2>&1 | grep -E "(Step|Successfully|ERROR|error)" | head -20

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "❌ Docker build failed!"
    exit 1
fi

echo "✅ Docker image built successfully"
cd ..

# Step 4: Push to ACR
echo ""
echo "📤 Step 4/5: Pushing image to Azure Container Registry..."
echo "$ACR_PASSWORD" | docker login "$ACR_LOGIN_SERVER" -u "$ACR_USERNAME" --password-stdin > /dev/null 2>&1

docker push "$ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG" 2>&1 | grep -E "(Pushing|pushed|ERROR|error)" | head -10

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "❌ Docker push failed!"
    exit 1
fi

echo "✅ Image pushed to ACR"

# Step 5: Configure App Service to use Docker
echo ""
echo "⚙️  Step 5/5: Configuring App Service to use Docker..."
az webapp config container set \
    --name "$APP_SERVICE_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --docker-custom-image-name "$ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG" \
    --docker-registry-server-url "https://$ACR_LOGIN_SERVER" \
    --docker-registry-server-user "$ACR_USERNAME" \
    --docker-registry-server-password "$ACR_PASSWORD" \
    > /dev/null 2>&1

echo "✅ App Service configured to use Docker"

# Restart the app
echo ""
echo "🔄 Restarting App Service..."
az webapp restart --name "$APP_SERVICE_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ Deployment Complete (No Oryx!)"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "🔗 Backend URL: https://$APP_SERVICE_NAME.azurewebsites.net"
echo ""
echo "⏳ Waiting 30 seconds for container to start..."
sleep 30

# Test
echo ""
echo "🧪 Testing backend..."
for i in {1..10}; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "https://$APP_SERVICE_NAME.azurewebsites.net/health" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo ""
        echo "✅✅✅ BACKEND IS WORKING! (HTTP $HTTP_CODE)"
        echo ""
        curl -s --max-time 5 "https://$APP_SERVICE_NAME.azurewebsites.net/health" | python3 -m json.tool 2>/dev/null
        echo ""
        echo "✅ Deployment successful - no Oryx needed!"
        exit 0
    else
        echo "   Check $i/10... (HTTP $HTTP_CODE)"
        sleep 6
    fi
done

echo ""
echo "⚠️  Backend not responding yet. Check Azure Portal logs."
echo "   Container may need a few more minutes to start."


