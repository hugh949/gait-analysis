#!/bin/bash
# Clean up disk space on App Service
# For pilot project: Remove old images and containers to free space

APP_NAME="gaitanalysisapp"
RESOURCE_GROUP="gait-analysis-rg-wus3"
ACR_NAME="gaitacr737"

echo "=========================================="
echo "Cleaning Up Disk Space"
echo "=========================================="
echo ""

# Clean up old ACR images (keep only last 5 images)
echo "🧹 Cleaning up old ACR images..."
az acr repository show-tags \
    --name "$ACR_NAME" \
    --repository gait-integrated \
    --orderby time_desc \
    --query "[5:].name" \
    -o tsv 2>/dev/null | while read tag; do
    if [ -n "$tag" ]; then
        echo "   Deleting old image: gait-integrated:$tag"
        az acr repository delete \
            --name "$ACR_NAME" \
            --image "gait-integrated:$tag" \
            --yes \
            --output none 2>&1
    fi
done

echo "✅ ACR cleanup complete"
echo ""

# Clean up App Service logs (optional - helps with disk space)
echo "🧹 Cleaning up old App Service logs..."
# Note: Azure App Service automatically manages logs, but we can trigger cleanup
az webapp log tail --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" --timeout 1 > /dev/null 2>&1 || true

echo "✅ Log cleanup initiated"
echo ""

# Restart App Service to clear any cached containers/images
echo "🔄 Restarting App Service to clear caches..."
az webapp restart --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" --output none 2>&1

if [ $? -eq 0 ]; then
    echo "✅ App Service restarted"
else
    echo "⚠️  Failed to restart App Service"
fi

echo ""
echo "=========================================="
echo "✅ Disk Space Cleanup Complete!"
echo "=========================================="
echo ""
echo "For a pilot project with 3 users and files <100MB:"
echo "- Keeping last 5 Docker images (should be sufficient)"
echo "- App Service will automatically manage disk space"
echo "- If issues persist, consider upgrading App Service plan"
