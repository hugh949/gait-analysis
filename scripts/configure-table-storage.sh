#!/bin/bash
# Configure Azure Table Storage for analysis metadata
# This is more reliable than file-based mock storage

APP_NAME="gaitanalysisapp"
RESOURCE_GROUP="gait-analysis-rg-wus3"

echo "=========================================="
echo "Configuring Azure Table Storage"
echo "=========================================="
echo ""

# Get storage account
STORAGE_ACCOUNT=$(az storage account list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null)

if [ -z "$STORAGE_ACCOUNT" ]; then
    echo "❌ No storage account found in resource group $RESOURCE_GROUP"
    echo "   Please create a storage account first or check the resource group name"
    exit 1
fi

echo "✅ Found storage account: $STORAGE_ACCOUNT"

# Get connection string
STORAGE_CONN=$(az storage account show-connection-string \
    --name "$STORAGE_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" \
    --query connectionString -o tsv 2>/dev/null)

if [ -z "$STORAGE_CONN" ]; then
    echo "❌ Failed to get storage connection string"
    exit 1
fi

echo "✅ Retrieved storage connection string"
echo ""

# Check if connection string is already set
CURRENT_CONN=$(az webapp config appsettings list \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "[?name=='AZURE_STORAGE_CONNECTION_STRING'].value" -o tsv 2>/dev/null)

if [ -n "$CURRENT_CONN" ]; then
    echo "⚠️  Storage connection string already configured"
    echo "   Updating to ensure it's correct..."
fi

# Set the connection string
echo "📝 Setting AZURE_STORAGE_CONNECTION_STRING in App Service..."
az webapp config appsettings set \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --settings AZURE_STORAGE_CONNECTION_STRING="$STORAGE_CONN" \
    --output none 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Storage connection string configured successfully"
    echo ""
    echo "The app will now use Azure Table Storage for analysis metadata."
    echo "This is more reliable than file-based storage and works across all workers."
    echo ""
    echo "Next steps:"
    echo "1. The app will automatically create the 'gaitanalyses' table on first use"
    echo "2. Restart the app service to apply changes:"
    echo "   az webapp restart --name $APP_NAME --resource-group $RESOURCE_GROUP"
else
    echo "❌ Failed to set storage connection string"
    exit 1
fi
