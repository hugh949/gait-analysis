#!/bin/bash
# Create Azure resources for Microsoft Native Architecture
# Minimal setup - just what we need

set -e

RESOURCE_GROUP="gait-analysis-rg-wus3"
LOCATION="westus3"
APP_NAME="gait-analysis-native"

echo "🚀 Creating Azure Resources for Native Architecture"
echo "===================================================="
echo ""
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo ""

# Step 1: Create Blob Storage Account
echo "📦 Step 1/4: Creating Azure Blob Storage..."
STORAGE_ACCOUNT="${APP_NAME}stor${RANDOM:0:6}"
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --access-tier Hot \
  --https-only true \
  --min-tls-version TLS1_2 \
  > /dev/null 2>&1

echo "✅ Storage Account created: $STORAGE_ACCOUNT"

# Create container for videos
az storage container create \
  --name videos \
  --account-name "$STORAGE_ACCOUNT" \
  --auth-mode login \
  > /dev/null 2>&1

echo "✅ Container 'videos' created"

# Get connection string
STORAGE_CONNECTION_STRING=$(az storage account show-connection-string \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query connectionString -o tsv)

echo "✅ Storage connection string retrieved"
echo ""

# Step 2: Create Computer Vision resource
echo "👁️  Step 2/4: Creating Azure Computer Vision..."
COMPUTER_VISION_NAME="${APP_NAME}-vision-${RANDOM:0:6}"
az cognitiveservices account create \
  --name "$COMPUTER_VISION_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --kind ComputerVision \
  --sku S1 \
  --location "$LOCATION" \
  > /dev/null 2>&1

echo "✅ Computer Vision created: $COMPUTER_VISION_NAME"

# Get keys and endpoint
CV_KEY=$(az cognitiveservices account keys list \
  --name "$COMPUTER_VISION_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query key1 -o tsv)

CV_ENDPOINT=$(az cognitiveservices account show \
  --name "$COMPUTER_VISION_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query properties.endpoint -o tsv)

echo "✅ Computer Vision keys retrieved"
echo ""

# Step 3: Create Azure SQL Database
echo "💾 Step 3/4: Creating Azure SQL Database..."
SQL_SERVER_NAME="${APP_NAME}-sql-${RANDOM:0:6}"
SQL_ADMIN_USER="gaitadmin"
SQL_ADMIN_PASSWORD="GaitAnalysis${RANDOM}!2026"

az sql server create \
  --name "$SQL_SERVER_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --admin-user "$SQL_ADMIN_USER" \
  --admin-password "$SQL_ADMIN_PASSWORD" \
  > /dev/null 2>&1

echo "✅ SQL Server created: $SQL_SERVER_NAME"

# Allow Azure services to access
az sql server firewall-rule create \
  --resource-group "$RESOURCE_GROUP" \
  --server "$SQL_SERVER_NAME" \
  --name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0 \
  > /dev/null 2>&1

echo "✅ Firewall rule configured"

# Create database
az sql db create \
  --resource-group "$RESOURCE_GROUP" \
  --server "$SQL_SERVER_NAME" \
  --name gaitanalysis \
  --service-objective Basic \
  --backup-storage-redundancy Local \
  > /dev/null 2>&1

echo "✅ Database 'gaitanalysis' created"
echo ""

# Step 4: Save configuration
echo "💾 Step 4/4: Saving configuration..."
cat > backend/.env.azure-native << EOF
# Azure Native Architecture Configuration
# Generated: $(date)

# Blob Storage
AZURE_STORAGE_ACCOUNT_NAME=$STORAGE_ACCOUNT
AZURE_STORAGE_CONNECTION_STRING=$STORAGE_CONNECTION_STRING
AZURE_STORAGE_CONTAINER_NAME=videos

# Computer Vision
AZURE_COMPUTER_VISION_KEY=$CV_KEY
AZURE_COMPUTER_VISION_ENDPOINT=$CV_ENDPOINT

# SQL Database
AZURE_SQL_SERVER=$SQL_SERVER_NAME.database.windows.net
AZURE_SQL_DATABASE=gaitanalysis
AZURE_SQL_USER=$SQL_ADMIN_USER
AZURE_SQL_PASSWORD=$SQL_ADMIN_PASSWORD

# App Service Name (will be created separately)
AZURE_APP_SERVICE_NAME=${APP_NAME}-api
EOF

echo "✅ Configuration saved to backend/.env.azure-native"
echo ""

echo "═══════════════════════════════════════════════════════════"
echo "✅ Azure Resources Created Successfully!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📋 Resources Created:"
echo "   ✅ Blob Storage: $STORAGE_ACCOUNT"
echo "   ✅ Computer Vision: $COMPUTER_VISION_NAME"
echo "   ✅ SQL Database: $SQL_SERVER_NAME/gaitanalysis"
echo ""
echo "💾 Configuration saved to: backend/.env.azure-native"
echo ""
echo "🔐 IMPORTANT: SQL Password is: $SQL_ADMIN_PASSWORD"
echo "   (Saved in backend/.env.azure-native)"
echo ""


