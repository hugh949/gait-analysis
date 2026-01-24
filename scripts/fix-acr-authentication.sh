#!/bin/bash
# Fix ACR authentication for App Service
# This ensures the App Service can pull Docker images from ACR

APP_NAME="gaitanalysisapp"
RESOURCE_GROUP="gait-analysis-rg-wus3"
ACR_NAME="gaitacr737"

echo "=========================================="
echo "Fixing ACR Authentication"
echo "=========================================="
echo ""

# Get ACR credentials
echo "📝 Getting ACR credentials..."
ACR_LOGIN=$(az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query loginServer -o tsv)
ACR_USER=$(az acr credential show --name "$ACR_NAME" --query username -o tsv)
ACR_PASS=$(az acr credential show --name "$ACR_NAME" --query passwords[0].value -o tsv)

if [ -z "$ACR_LOGIN" ] || [ -z "$ACR_USER" ] || [ -z "$ACR_PASS" ]; then
    echo "❌ Failed to get ACR credentials"
    exit 1
fi

echo "✅ ACR Login Server: $ACR_LOGIN"
echo "✅ ACR Username: $ACR_USER"
echo ""

# Get current image name
CURRENT_IMAGE=$(az webapp config container show \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query dockerImageName -o tsv 2>/dev/null)

if [ -n "$CURRENT_IMAGE" ]; then
    echo "📦 Current Docker image: $CURRENT_IMAGE"
else
    echo "⚠️  No Docker image configured"
fi

# Update container configuration with fresh credentials
echo ""
echo "⚙️  Updating App Service container configuration..."
if [ -n "$CURRENT_IMAGE" ]; then
    # Use current image if available
    IMAGE_NAME="$CURRENT_IMAGE"
else
    # Use latest tag if no image configured
    IMAGE_NAME="$ACR_LOGIN/gait-integrated:latest"
    echo "⚠️  No image configured, using: $IMAGE_NAME"
fi

az webapp config container set \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --container-image-name "$IMAGE_NAME" \
    --container-registry-url "https://$ACR_LOGIN" \
    --container-registry-user "$ACR_USER" \
    --container-registry-password "$ACR_PASS" \
    --output none 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Container configuration updated"
else
    echo "❌ Failed to update container configuration"
    exit 1
fi

# Also update app settings to ensure password is fresh
echo ""
echo "⚙️  Updating app settings..."
az webapp config appsettings set \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --settings \
    DOCKER_REGISTRY_SERVER_PASSWORD="$ACR_PASS" \
    DEPLOYMENT_TIMESTAMP="$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    --output none 2>&1

if [ $? -eq 0 ]; then
    echo "✅ App settings updated"
else
    echo "⚠️  Failed to update app settings (non-critical)"
fi

echo ""
echo "=========================================="
echo "✅ ACR Authentication Fixed!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Restart the App Service:"
echo "   az webapp restart --name $APP_NAME --resource-group $RESOURCE_GROUP"
echo ""
echo "2. The app should now be able to pull images from ACR"
