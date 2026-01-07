#!/bin/bash
# Simple deployment script - manual commands
# Run this directly in your terminal

set -e

echo "🚀 Simple Backend Deployment"
echo "============================"
echo ""

cd /Users/hughrashid/Cursor/Gait-Analysis/backend

echo "📦 Step 1/3: Creating deployment package..."
TEMP_DIR=$(mktemp -d)
DEPLOY_DIR="$TEMP_DIR/deploy"
mkdir -p "$DEPLOY_DIR"

echo "   • Copying files..."
cp -r app "$DEPLOY_DIR/"
cp main.py "$DEPLOY_DIR/"
cp requirements.txt "$DEPLOY_DIR/requirements.txt"
echo "3.11" > "$DEPLOY_DIR/.python_version"

# Add build trigger to force fresh build
BUILD_TIMESTAMP=$(date +%s)
echo "$BUILD_TIMESTAMP" > "$DEPLOY_DIR/.build_trigger"
echo "" >> "$DEPLOY_DIR/requirements.txt"
echo "# Build triggered at $(date) - Force fresh build $BUILD_TIMESTAMP" >> "$DEPLOY_DIR/requirements.txt"

echo "   ✅ Files copied"
echo ""

echo "📦 Step 2/3: Creating ZIP file..."
ZIP_FILE="/tmp/backend-deploy-$(date +%s).zip"
cd "$DEPLOY_DIR"
zip -r "$ZIP_FILE" . > /dev/null 2>&1

ZIP_SIZE=$(stat -f%z "$ZIP_FILE" 2>/dev/null || stat -c%s "$ZIP_FILE" 2>/dev/null)
ZIP_KB=$((ZIP_SIZE / 1024))
echo "   ✅ ZIP created: ${ZIP_KB} KB ($(du -h "$ZIP_FILE" | cut -f1))"
echo ""

echo "🚀 Step 3/3: Deploying to Azure..."
echo "   • Uploading ZIP file..."
echo "   • This may take 30-90 seconds..."
echo "   • Progress:"

az webapp deployment source config-zip \
  --name gait-analysis-api-simple \
  --resource-group gait-analysis-rg-wus3 \
  --src "$ZIP_FILE"

echo ""
echo "   ✅ Deployment command completed"
echo ""

# Cleanup
rm -rf "$TEMP_DIR"
echo "🧹 Cleaned up temporary files"
echo ""

echo "═══════════════════════════════════════════════════════════"
echo "✅ Deployment Complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "⏳ Next steps:"
echo "   1. Azure will process the deployment (1-2 minutes)"
echo "   2. Oryx will install dependencies (5-10 minutes for first build)"
echo "   3. Backend will start automatically"
echo ""
echo "🔍 Check status:"
echo "   az webapp deployment list --name gait-analysis-api-simple --resource-group gait-analysis-rg-wus3 --query '[0].{Time:startTime,Status:status}' -o table"
echo ""
echo "🌐 Test backend:"
echo "   curl https://gait-analysis-api-simple.azurewebsites.net/health"
echo ""



