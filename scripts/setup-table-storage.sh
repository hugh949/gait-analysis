#!/bin/bash
# Setup Azure Table Storage for reliable analysis metadata storage
# This fixes "Analysis not found" errors in multi-worker environments

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-gait-analysis-rg-wus3}"
LOCATION="${AZURE_LOCATION:-westus3}"
APP_NAME="gaitanalysisapp"

echo "=========================================="
echo "Setting up Azure Table Storage"
echo "=========================================="
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo ""

# Check if storage account exists
STORAGE_ACCOUNT=$(az storage account list --resource-group "$RESOURCE_GROUP" --query "[?contains(name, 'gait') || contains(name, 'storage')].name" -o tsv | head -1)

if [ -z "$STORAGE_ACCOUNT" ]; then
    echo "📦 Creating storage account..."
    STORAGE_ACCOUNT="gaitstorage$(date +%s | tail -c 6)"
    
    az storage account create \
        --name "$STORAGE_ACCOUNT" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --sku Standard_LRS \
        --kind StorageV2 \
        --output none 2>&1
    
    if [ $? -eq 0 ]; then
        echo "✅ Created storage account: $STORAGE_ACCOUNT"
    else
        echo "❌ Failed to create storage account"
        exit 1
    fi
else
    echo "✅ Found existing storage account: $STORAGE_ACCOUNT"
fi

# Get connection string
echo ""
echo "📝 Getting storage connection string..."
STORAGE_CONN=$(az storage account show-connection-string \
    --name "$STORAGE_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" \
    --query connectionString -o tsv 2>/dev/null)

if [ -z "$STORAGE_CONN" ]; then
    echo "❌ Failed to get storage connection string"
    exit 1
fi

echo "✅ Retrieved connection string"
echo ""

# Configure App Service
echo "⚙️  Configuring App Service..."
az webapp config appsettings set \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --settings AZURE_STORAGE_CONNECTION_STRING="$STORAGE_CONN" \
    --output none 2>&1

if [ $? -eq 0 ]; then
    echo "✅ App Service configured with storage connection string"
else
    echo "❌ Failed to configure App Service"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "The app will now use Azure Table Storage for analysis metadata."
echo "This is more reliable than file-based storage."
echo ""
echo "Next steps:"
echo "1. Restart the App Service:"
echo "   az webapp restart --name $APP_NAME --resource-group $RESOURCE_GROUP"
echo ""
echo "2. The app will automatically create the 'gaitanalyses' table on first use"
echo ""
echo "Cost: ~\$0.05/GB/month (very cheap for metadata storage)"
