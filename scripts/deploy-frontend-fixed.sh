#!/bin/bash
# Deploy frontend with fixed upload button

set -e

echo "🚀 Frontend Deployment"
echo "======================"
echo ""

cd "$(dirname "$0")/../frontend"

echo "📦 Step 1/3: Building frontend..."
npm run build

if [ $? -ne 0 ]; then
  echo "❌ Build failed"
  exit 1
fi

echo "✅ Build complete"
echo ""

echo "📋 Step 2/3: Checking build output..."
if [ ! -d "dist" ]; then
  echo "❌ dist directory not found"
  exit 1
fi

echo "   ✅ dist directory found"
ls -lh dist/ | head -10
echo ""

echo "🚀 Step 3/3: Deploying to Azure Static Web Apps..."
echo "   • Using deployment token from environment or Azure Portal"
echo ""

# Azure Static Web App deployment token
# Get this from: Azure Portal > Static Web App > Manage deployment token
DEPLOYMENT_TOKEN="${AZURE_STATIC_WEB_APPS_API_TOKEN:-1aaad346d4e5bd36241348cfca7dde044f070ae22516f876ea34bde2d6f6bcd201-0ab6484a-20a7-49f6-979d-bd3285fc68d000f21100a467810f}"

if [ -z "$DEPLOYMENT_TOKEN" ]; then
  echo "❌ Deployment token not found"
  echo "   Please set AZURE_STATIC_WEB_APPS_API_TOKEN environment variable"
  echo "   Or get it from Azure Portal: Static Web App > Manage deployment token"
  exit 1
fi

echo "   • Deploying dist folder..."
npx @azure/static-web-apps-cli deploy dist \
  --deployment-token "$DEPLOYMENT_TOKEN" \
  --env production

if [ $? -ne 0 ]; then
  echo "❌ Deployment failed"
  exit 1
fi

echo ""
echo "✅ Deployment complete!"
echo ""
echo "🔗 Frontend URL: https://jolly-meadow-0a467810f.1.azurestaticapps.net"
echo ""
echo "⏳ Wait 30-60 seconds for deployment to propagate"
echo "   Then test the upload button with a video file"
echo ""



