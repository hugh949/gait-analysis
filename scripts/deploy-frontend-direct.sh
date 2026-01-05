#!/bin/bash
# Direct Frontend Deployment from Cursor to Azure
# Bypasses GitHub - deploys local code directly to Azure Static Web Apps

set -e

echo "🚀 Direct Frontend Deployment to Azure"
echo "======================================"
echo ""

# Azure Static Web App deployment token
DEPLOYMENT_TOKEN="1aaad346d4e5bd36241348cfca7dde044f070ae22516f876ea34bde2d6f6bcd201-0ab6484a-20a7-49f6-979d-bd3285fc68d000f21100a467810f"

# Navigate to frontend directory
cd "$(dirname "$0")/../frontend"

echo "📦 Step 1/3: Building frontend..."
npm run build

if [ $? -ne 0 ]; then
  echo "❌ Build failed"
  exit 1
fi

echo "✅ Build complete"
echo ""

echo "🔧 Step 2/3: Deploying to Azure Static Web Apps..."
npx @azure/static-web-apps-cli deploy dist \
  --deployment-token "$DEPLOYMENT_TOKEN" \
  --env production

if [ $? -ne 0 ]; then
  echo "❌ Deployment failed"
  exit 1
fi

echo ""
echo "✅ Deployment complete!"
echo "🔗 App URL: https://jolly-meadow-0a467810f.1.azurestaticapps.net"
echo ""

