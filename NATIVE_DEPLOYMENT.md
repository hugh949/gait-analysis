# Native Backend Deployment (No Docker)

## Why Native Deployment?

### Docker Issues:
- ❌ Slow builds (5-10 minutes)
- ❌ Complex setup
- ❌ Container management overhead
- ❌ Build failures and debugging

### Native Deployment Benefits:
- ✅ **Fast deployment** (1-2 minutes)
- ✅ **Simple process** (just ZIP upload)
- ✅ **Azure handles Python** environment
- ✅ **Easy updates** (no rebuild needed)
- ✅ **Better for development** (faster iteration)

## How It Works

1. **ZIP Deployment**: Package code and upload to Azure
2. **Azure Oryx Build**: Azure automatically installs dependencies
3. **Python Runtime**: Azure provides Python 3.11 runtime
4. **Startup Script**: Runs `uvicorn main:app` on startup

## Deployment Methods

### Method 1: Native ZIP Deployment (Recommended)

```bash
./scripts/deploy-backend-native.sh
```

**Time:** 1-2 minutes (vs 5-10 minutes with Docker)

### Method 2: Manual ZIP Deployment

```bash
cd backend
zip -r deploy.zip . -x "*.git*" "*.pyc" "__pycache__/*"
az webapp deployment source config-zip \
  --name gait-analysis-api-simple \
  --resource-group gait-analysis-rg-wus3 \
  --src deploy.zip
```

### Method 3: Git Deployment

```bash
az webapp deployment source config-local-git \
  --name gait-analysis-api-simple \
  --resource-group gait-analysis-rg-wus3
```

## Configuration

### App Service Settings

**Python Version:**
```bash
az webapp config set --name gait-analysis-api-simple \
  --resource-group gait-analysis-rg-wus3 \
  --linux-fx-version "PYTHON|3.11"
```

**Startup Command:**
```bash
az webapp config set --name gait-analysis-api-simple \
  --resource-group gait-analysis-rg-wus3 \
  --startup-file "startup.sh"
```

**Environment Variables:**
Set in Azure Portal or via CLI:
```bash
az webapp config appsettings set \
  --name gait-analysis-api-simple \
  --resource-group gait-analysis-rg-wus3 \
  --settings \
    AZURE_COSMOS_ENDPOINT="..." \
    AZURE_COSMOS_KEY="..." \
    CORS_ORIGINS="..."
```

## Comparison

| Feature | Docker | Native |
|---------|--------|--------|
| Build Time | 5-10 min | 1-2 min |
| Update Speed | Slow | Fast |
| Complexity | High | Low |
| Dependencies | Manual | Auto |
| Debugging | Hard | Easy |
| Best For | Production | Development |

## Migration Steps

1. ✅ Created `startup.sh` for native deployment
2. ✅ Created `deploy-backend-native.sh` script
3. ⏳ Configure App Service for Python runtime
4. ⏳ Deploy using native method
5. ⏳ Test and verify

## Notes

- **First deployment** may take 3-5 minutes (installing dependencies)
- **Subsequent deployments** are very fast (1-2 minutes)
- **Dependencies** are installed automatically by Azure Oryx
- **No Docker** required - Azure handles the Python environment



