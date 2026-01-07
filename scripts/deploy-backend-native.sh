#!/bin/bash
# Native Backend Deployment (No Docker) - Direct ZIP deployment to Azure App Service
# Much faster than Docker builds!

set -e

echo "🚀 Native Backend Deployment to Azure (No Docker)"
echo "=================================================="
echo ""

RESOURCE_GROUP="gait-analysis-rg-wus3"
APP_SERVICE_NAME="gait-analysis-api-simple"

# Navigate to backend directory
cd "$(dirname "$0")/../backend"

echo "📋 Step 1/6: Preparing deployment package..."
echo "   • Checking Python version..."
python3 --version 2>&1 || echo "   ⚠️  Python3 not found locally (will use Azure's Python)"

echo ""
echo "📋 Step 2/6: Creating deployment ZIP..."
echo "   • Excluding unnecessary files..."

# Create a temporary directory for deployment
TEMP_DIR=$(mktemp -d)
DEPLOY_DIR="$TEMP_DIR/deploy"

mkdir -p "$DEPLOY_DIR"

# Copy necessary files
echo "   • Copying application files..."
cp -r app "$DEPLOY_DIR/"
cp main.py "$DEPLOY_DIR/"
cp requirements.txt "$DEPLOY_DIR/"
cp startup.sh "$DEPLOY_DIR/"
chmod +x "$DEPLOY_DIR/startup.sh"

# Create .deployment file for App Service
echo "   • Creating deployment configuration..."
cat > "$DEPLOY_DIR/.deployment" << EOF
[config]
SCM_DO_BUILD_DURING_DEPLOYMENT=true
ENABLE_ORYX_BUILD=true
EOF

# Create ZIP file
ZIP_FILE="/tmp/backend-deploy-$(date +%s).zip"
cd "$DEPLOY_DIR"
zip -r "$ZIP_FILE" . > /dev/null 2>&1

echo "   ✅ Deployment package created: $(du -h "$ZIP_FILE" | cut -f1)"
echo ""

echo "📋 Step 3/6: Configuring App Service for Python..."
echo "   • Setting Python version..."
az webapp config set --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP \
  --linux-fx-version "PYTHON|3.11" 2>&1 | grep -v "^$" || true

echo "   • Setting startup command..."
az webapp config set --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP \
  --startup-file "startup.sh" 2>&1 | grep -v "^$" || true

echo "   ✅ App Service configured for Python"
echo ""

echo "📋 Step 4/6: Uploading deployment package..."
echo "   • This may take 1-2 minutes..."
az webapp deployment source config-zip \
  --name $APP_SERVICE_NAME \
  --resource-group $RESOURCE_GROUP \
  --src "$ZIP_FILE" 2>&1 | tail -10

if [ $? -ne 0 ]; then
  echo "   ❌ Deployment failed"
  rm -rf "$TEMP_DIR" "$ZIP_FILE"
  exit 1
fi

echo "   ✅ Package uploaded"
echo ""

echo "📋 Step 5/6: Installing Python dependencies..."
echo "   • Azure will install packages from requirements.txt"
echo "   • This may take 3-5 minutes for first deployment..."
echo "   • Monitoring build logs..."

# Wait for deployment to complete
echo "   ⏳ Waiting for deployment to process..."
sleep 10

echo "   ✅ Dependencies installation in progress"
echo ""

echo "📋 Step 6/6: Waiting for application to start..."
echo "   • Checking health endpoint..."

# Wait with progress updates
for i in {1..12}; do
  sleep 10
  echo "   ⏱️  Waited $(($i * 10)) seconds... ($(($i * 10))/120)"
  
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://$APP_SERVICE_NAME.azurewebsites.net/ 2>/dev/null || echo "000")
  
  if [ "$HTTP_CODE" = "200" ]; then
    echo ""
    echo "   ✅ Application is responding! (HTTP $HTTP_CODE)"
    break
  elif [ "$HTTP_CODE" != "000" ] && [ "$HTTP_CODE" != "503" ]; then
    echo "   ⚠️  Application returned HTTP $HTTP_CODE (may still be starting)"
  fi
done

# Cleanup
rm -rf "$TEMP_DIR" "$ZIP_FILE"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ Native Deployment Complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "🔗 Backend URL: https://$APP_SERVICE_NAME.azurewebsites.net"
echo ""
echo "💡 Benefits of Native Deployment:"
echo "   • No Docker build time (instant deployment)"
echo "   • Faster updates (just ZIP upload)"
echo "   • Simpler deployment process"
echo "   • Azure handles Python environment"
echo ""



