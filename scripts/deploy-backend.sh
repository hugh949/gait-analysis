#!/bin/bash
# Backend Deployment Script with Versioning
# This script ensures reliable backend deployments with proper versioning

set -e

RESOURCE_GROUP="gait-analysis-rg-wus3"
CONTAINER_APP="gait-analysis-api-wus3"
REGISTRY="gaitanalysisacrwus3"
IMAGE_NAME="gait-analysis-api"

# Generate version tag based on timestamp
VERSION_TAG="v$(date +%Y%m%d-%H%M%S)"

echo "🚀 Starting backend deployment..."
echo "📦 Version: $VERSION_TAG"

# Step 1: Build image with version tag
echo "🔨 Step 1/5: Building Docker image..."
cd "$(dirname "$0")/../backend"
az acr build --registry $REGISTRY --image $IMAGE_NAME:$VERSION_TAG --image $IMAGE_NAME:latest . || {
    echo "❌ Build failed"
    exit 1
}
echo "✅ Build completed"

# Step 2: Update container app with versioned image
echo "🔄 Step 2/5: Updating container app with versioned image..."
az containerapp update \
    --name $CONTAINER_APP \
    --resource-group $RESOURCE_GROUP \
    --image $REGISTRY.azurecr.io/$IMAGE_NAME:$VERSION_TAG \
    --min-replicas 1 \
    --max-replicas 5 || {
    echo "❌ Container app update failed"
    exit 1
}
echo "✅ Container app updated"

# Step 3: Wait for new revision
echo "⏳ Step 3/5: Waiting for new revision (60 seconds)..."
sleep 60

# Step 4: Check revision status
echo "🔍 Step 4/5: Checking revision status..."
LATEST_REVISION=$(az containerapp revision list \
    --name $CONTAINER_APP \
    --resource-group $RESOURCE_GROUP \
    --query "[0].name" -o tsv)

echo "Latest revision: $LATEST_REVISION"

# Step 5: Verify health
echo "🔍 Step 5/5: Verifying backend health..."
BACKEND_URL="https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io"

for i in {1..12}; do
    if curl -s -f -m 10 "$BACKEND_URL/" > /dev/null 2>&1; then
        echo "✅ Backend is healthy and responding!"
        exit 0
    fi
    echo "  Attempt $i/12: Waiting for backend..."
    sleep 10
done

echo "❌ Backend health check failed after 2 minutes"
exit 1



