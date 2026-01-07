#!/bin/bash
# Emergency Backend Fix - Get it working NOW
# This script does everything needed to get backend responding

set -e

RESOURCE_GROUP="gait-analysis-rg-wus3"
APP_SERVICE_NAME="gait-analysis-api-simple"
REGISTRY="gaitanalysisacrwus3"
IMAGE="gait-analysis-api:latest"

echo "🚨 EMERGENCY BACKEND FIX"
echo "========================"
echo ""

# Step 1: Ensure Docker is configured
echo "Step 1/5: Ensuring Docker configuration..."
az webapp config set \
  --name $APP_SERVICE_NAME \
  --resource-group $RESOURCE_GROUP \
  --linux-fx-version "DOCKER|${REGISTRY}.azurecr.io/${IMAGE}" \
  > /dev/null 2>&1

# Step 2: Get and set ACR credentials
echo "Step 2/5: Configuring ACR authentication..."
REGISTRY_USER=$(az acr credential show --name $REGISTRY --query "username" -o tsv)
REGISTRY_PASS=$(az acr credential show --name $REGISTRY --query "passwords[0].value" -o tsv)

az webapp config container set \
  --name $APP_SERVICE_NAME \
  --resource-group $RESOURCE_GROUP \
  --container-image-name "${REGISTRY}.azurecr.io/${IMAGE}" \
  --container-registry-url "https://${REGISTRY}.azurecr.io" \
  --container-registry-user "$REGISTRY_USER" \
  --container-registry-password "$REGISTRY_PASS" \
  > /dev/null 2>&1

# Step 3: Ensure CORS
echo "Step 3/5: Setting CORS..."
az webapp config appsettings set \
  --name $APP_SERVICE_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings \
    CORS_ORIGINS="https://jolly-meadow-0a467810f.1.azurestaticapps.net,http://localhost:3000,http://localhost:5173" \
  > /dev/null 2>&1

# Step 4: Ensure Always-On
echo "Step 4/5: Enabling Always-On..."
az webapp config set \
  --name $APP_SERVICE_NAME \
  --resource-group $RESOURCE_GROUP \
  --always-on true \
  > /dev/null 2>&1

# Step 5: Restart and wait
echo "Step 5/5: Restarting and waiting for health..."
az webapp restart --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP > /dev/null 2>&1

echo ""
echo "Waiting for container to start (this can take 2-3 minutes for first pull)..."
echo ""

for i in {1..12}; do
  sleep 10
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://${APP_SERVICE_NAME}.azurewebsites.net/health 2>/dev/null || echo "000")
  
  if [ "$HTTP_CODE" = "200" ]; then
    echo ""
    echo "✅✅✅ BACKEND IS WORKING! ✅✅✅"
    echo ""
    echo "Health check response:"
    curl -s --max-time 5 https://${APP_SERVICE_NAME}.azurewebsites.net/health
    echo ""
    exit 0
  fi
  
  echo "  Attempt $i/12: HTTP $HTTP_CODE (waiting...)"
done

echo ""
echo "⚠️  Backend not responding after 2 minutes"
echo "   • Container may still be pulling image (first time takes 3-5 minutes)"
echo "   • Check logs: az webapp log tail --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP"
echo ""


