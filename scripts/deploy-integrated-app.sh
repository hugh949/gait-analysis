#!/bin/bash
# Deploy Integrated Application (Frontend + Backend)
# Single URL, Single App Service, West US 3
# Microsoft Native Architecture

set -e

RESOURCE_GROUP="gait-analysis-rg-wus3"
LOCATION="westus3"
APP_NAME="gait-analysis-app"
PLAN_NAME="gait-analysis-plan"
REGISTRY="gaitanalysisacr$(date +%s | tail -c 4)"
IMAGE_NAME="gait-analysis-integrated"
IMAGE_TAG="latest"

echo "🚀 Deploying Integrated Gait Analysis Application"
echo "===================================================="
echo ""
echo "Architecture:"
echo "  ✅ Single App Service (API + Frontend)"
echo "  ✅ Single URL for everything"
echo "  ✅ All resources in West US 3"
echo "  ✅ Microsoft native services"
echo ""

# Step 1: Create Resource Group
echo "📦 Step 1/8: Creating Resource Group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" > /dev/null 2>&1
echo "✅ Resource Group: $RESOURCE_GROUP"

# Step 2: Create Azure Services
echo ""
echo "☁️  Step 2/8: Creating Azure Services..."

# Blob Storage
echo "   Creating Blob Storage..."
STORAGE_ACCOUNT="${APP_NAME}stor$(date +%s | tail -c 4)"
az storage account create \
    --name "$STORAGE_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --sku Standard_LRS \
    --kind StorageV2 \
    --https-only true \
    > /dev/null 2>&1

az storage container create \
    --name videos \
    --account-name "$STORAGE_ACCOUNT" \
    --auth-mode login \
    > /dev/null 2>&1

echo "   ✅ Blob Storage: $STORAGE_ACCOUNT"

# Computer Vision
echo "   Creating Computer Vision..."
CV_NAME="${APP_NAME}-vision-$(date +%s | tail -c 4)"
az cognitiveservices account create \
    --name "$CV_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --kind ComputerVision \
    --sku S1 \
    --location "$LOCATION" \
    > /dev/null 2>&1

echo "   ✅ Computer Vision: $CV_NAME"

# SQL Database
echo "   Creating SQL Database..."
SQL_SERVER="${APP_NAME}-sql-$(date +%s | tail -c 4)"
SQL_USER="gaitadmin"
SQL_PASSWORD="Gait${RANDOM:0:4}!2026"

az sql server create \
    --name "$SQL_SERVER" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --admin-user "$SQL_USER" \
    --admin-password "$SQL_PASSWORD" \
    > /dev/null 2>&1

az sql server firewall-rule create \
    --resource-group "$RESOURCE_GROUP" \
    --server "$SQL_SERVER" \
    --name AllowAzureServices \
    --start-ip-address 0.0.0.0 \
    --end-ip-address 0.0.0.0 \
    > /dev/null 2>&1

az sql db create \
    --resource-group "$RESOURCE_GROUP" \
    --server "$SQL_SERVER" \
    --name gaitanalysis \
    --service-objective Basic \
    > /dev/null 2>&1

echo "   ✅ SQL Database: $SQL_SERVER/gaitanalysis"

# Step 3: Create App Service Plan
echo ""
echo "📋 Step 3/8: Creating App Service Plan..."
az appservice plan create \
    --name "$PLAN_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --sku B1 \
    --is-linux \
    > /dev/null 2>&1

echo "✅ App Service Plan: $PLAN_NAME"

# Step 4: Create App Service
echo ""
echo "🌐 Step 4/8: Creating App Service..."
az webapp create \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --plan "$PLAN_NAME" \
    --runtime "PYTHON|3.11" \
    > /dev/null 2>&1

echo "✅ App Service: $APP_NAME"

# Step 5: Create ACR
echo ""
echo "📦 Step 5/8: Creating Azure Container Registry..."
az acr create \
    --name "$REGISTRY" \
    --resource-group "$RESOURCE_GROUP" \
    --sku Basic \
    --admin-enabled true \
    > /dev/null 2>&1

echo "✅ ACR: $REGISTRY"

# Step 6: Build Frontend
echo ""
echo "🔨 Step 6/8: Building Frontend..."
cd frontend
npm run build > /dev/null 2>&1
cd ..
echo "✅ Frontend built"

# Step 7: Build and Push Docker Image
echo ""
echo "🐳 Step 7/8: Building Docker Image (API + Frontend)..."
ACR_LOGIN_SERVER=$(az acr show --name "$REGISTRY" --query loginServer -o tsv)

cd backend
az acr build \
    --registry "$REGISTRY" \
    --image "$IMAGE_NAME:$IMAGE_TAG" \
    --file Dockerfile.integrated \
    . 2>&1 | grep -E "(Step|Successfully|Pushing|ERROR)" | tail -20

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "❌ Docker build failed!"
    exit 1
fi

echo "✅ Docker image built and pushed"
cd ..

# Step 8: Configure App Service
echo ""
echo "⚙️  Step 8/8: Configuring App Service..."

# Get credentials
ACR_USERNAME=$(az acr credential show --name "$REGISTRY" --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name "$REGISTRY" --query passwords[0].value -o tsv)

# Configure container
az webapp config container set \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --docker-custom-image-name "$ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG" \
    --docker-registry-server-url "https://$ACR_LOGIN_SERVER" \
    --docker-registry-server-user "$ACR_USERNAME" \
    --docker-registry-server-password "$ACR_PASSWORD" \
    > /dev/null 2>&1

# Get connection strings
STORAGE_CONN=$(az storage account show-connection-string --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" --query connectionString -o tsv)
CV_KEY=$(az cognitiveservices account keys list --name "$CV_NAME" --resource-group "$RESOURCE_GROUP" --query key1 -o tsv)
CV_ENDPOINT=$(az cognitiveservices account show --name "$CV_NAME" --resource-group "$RESOURCE_GROUP" --query properties.endpoint -o tsv)

# Set environment variables
az webapp config appsettings set \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --settings \
    AZURE_STORAGE_CONNECTION_STRING="$STORAGE_CONN" \
    AZURE_STORAGE_CONTAINER_NAME="videos" \
    AZURE_COMPUTER_VISION_KEY="$CV_KEY" \
    AZURE_COMPUTER_VISION_ENDPOINT="$CV_ENDPOINT" \
    AZURE_SQL_SERVER="$SQL_SERVER.database.windows.net" \
    AZURE_SQL_DATABASE="gaitanalysis" \
    AZURE_SQL_USER="$SQL_USER" \
    AZURE_SQL_PASSWORD="$SQL_PASSWORD" \
    CORS_ORIGINS="https://$APP_NAME.azurewebsites.net,http://localhost:3000,http://localhost:5173" \
    > /dev/null 2>&1

# Enable Always-On
az webapp config set \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --always-on true \
    > /dev/null 2>&1

echo "✅ App Service configured"

# Restart
echo ""
echo "🔄 Restarting App Service..."
az webapp restart --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ Deployment Complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "🔗 Single Application URL:"
echo "   https://$APP_NAME.azurewebsites.net"
echo ""
echo "⏳ Waiting 60 seconds for container to start..."
sleep 60

# Test
echo ""
echo "🧪 Testing application..."
for i in {1..15}; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "https://$APP_NAME.azurewebsites.net/health" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo ""
        echo "✅✅✅ APPLICATION IS WORKING! (HTTP $HTTP_CODE)"
        echo ""
        curl -s --max-time 5 "https://$APP_NAME.azurewebsites.net/health" | python3 -m json.tool 2>/dev/null
        echo ""
        echo "✅ Integrated application deployed successfully!"
        echo "🔗 URL: https://$APP_NAME.azurewebsites.net"
        exit 0
    else
        echo "   Check $i/15... (HTTP $HTTP_CODE)"
        sleep 8
    fi
done

echo ""
echo "⚠️  Application not responding yet. Check Azure Portal logs."
echo "   Container may need a few more minutes to start."


