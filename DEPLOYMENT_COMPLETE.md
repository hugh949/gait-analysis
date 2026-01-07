# Production Deployment - Current Status

## ✅ Successfully Deployed

### Core Infrastructure
1. **Resource Group**: `gait-analysis-rg` ✅
2. **Storage Account**: `gaitanalysisprodstor` ✅
3. **Cosmos DB**: `gaitanalysisprodcosmos` ✅
4. **Key Vault**: `gaitanalysis-kv-prod` ✅
5. **Container Apps Environment**: `gait-analysis-env` ✅
6. **Container Registry**: `gaitanalysisacr` ✅
7. **Static Web App**: `gait-analysis-web` ✅
   - URL: https://gentle-wave-0d4e1d10f.4.azurestaticapps.net
8. **Function App**: `gait-analysis-api` ✅
   - URL: https://gait-analysis-api.azurewebsites.net

### Frontend
- ✅ Built successfully
- ✅ Ready for deployment
- Location: `frontend/dist/`

### Backend
- ⏳ Docker image building in progress
- ⏳ Container app deployment pending

## 🚧 Deployment Steps Remaining

### 1. Complete Docker Image Build

Check build status:
```bash
az acr task list-runs --registry gaitanalysisacr --output table
```

If build failed, rebuild:
```bash
cd backend
az acr build --registry gaitanalysisacr --image gait-analysis-api:latest .
```

### 2. Deploy Container App

Once image is ready, run:
```bash
./azure/deploy-container-app.sh
```

Or manually:
```bash
# Get connection strings
STORAGE_CONN=$(az storage account show-connection-string --name gaitanalysisprodstor --resource-group gait-analysis-rg --query connectionString -o tsv)
COSMOS_ENDPOINT=$(az cosmosdb show --name gaitanalysisprodcosmos --resource-group gait-analysis-rg --query documentEndpoint -o tsv)
COSMOS_KEY=$(az cosmosdb keys list --name gaitanalysisprodcosmos --resource-group gait-analysis-rg --query primaryMasterKey -o tsv)

# Get ACR credentials
ACR_USER=$(az acr credential show --name gaitanalysisacr --query username -o tsv)
ACR_PASS=$(az acr credential show --name gaitanalysisacr --query passwords[0].value -o tsv)

# Deploy
az containerapp create \
  --name gait-analysis-api \
  --resource-group gait-analysis-rg \
  --environment gait-analysis-env \
  --image gaitanalysisacr.azurecr.io/gait-analysis-api:latest \
  --registry-server gaitanalysisacr.azurecr.io \
  --registry-username "$ACR_USER" \
  --registry-password "$ACR_PASS" \
  --target-port 8000 \
  --ingress external \
  --cpu 1.0 \
  --memory 2.0Gi \
  --min-replicas 0 \
  --max-replicas 5 \
  --env-vars \
    AZURE_STORAGE_CONNECTION_STRING="$STORAGE_CONN" \
    AZURE_STORAGE_CONTAINER="gait-videos" \
    AZURE_COSMOS_ENDPOINT="$COSMOS_ENDPOINT" \
    AZURE_COSMOS_KEY="$COSMOS_KEY" \
    AZURE_COSMOS_DATABASE="gait-analysis-db"
```

### 3. Deploy Frontend to Static Web App

Static Web Apps typically use GitHub Actions for deployment. Options:

**Option A: Use GitHub Actions (Recommended)**
1. Push code to GitHub
2. Static Web App will auto-deploy via GitHub Actions

**Option B: Manual Upload**
1. Use Azure Portal → Static Web App → Deployment Center
2. Upload the `dist` folder contents

**Option C: Use SWA CLI**
```bash
npm install -g @azure/static-web-apps-cli
swa deploy ./frontend/dist --deployment-token <token> --env production
```

Get deployment token:
```bash
az staticwebapp secrets list --name gait-analysis-web --resource-group gait-analysis-rg
```

### 4. Update Frontend API URL

Once Container App is deployed, get its URL:
```bash
az containerapp show \
  --name gait-analysis-api \
  --resource-group gait-analysis-rg \
  --query properties.configuration.ingress.fqdn -o tsv
```

Update frontend environment variable:
- Set `VITE_API_URL` to Container App URL
- Rebuild and redeploy frontend

## Current URLs

- **Frontend**: https://gentle-wave-0d4e1d10f.4.azurestaticapps.net
- **Backend (Container App)**: Will be available after deployment
- **Backend (Function App)**: https://gait-analysis-api.azurewebsites.net (needs code adaptation)

## Next Actions

1. ✅ Infrastructure deployed
2. ✅ Frontend built
3. ⏳ Wait for Docker build to complete
4. ⏳ Deploy Container App
5. ⏳ Deploy Frontend to Static Web App
6. ⏳ Update frontend API URL
7. ⏳ Test end-to-end

## Troubleshooting

### Docker Build Issues
- Check build logs: `az acr task logs --registry gaitanalysisacr --run-id <run-id>`
- Fix any dependency issues in `requirements.txt`
- Rebuild if needed

### Container App Deployment
- Ensure image exists in ACR
- Verify ACR credentials
- Check environment variables are set correctly

### Static Web App Deployment
- Use GitHub Actions for automatic deployment
- Or use SWA CLI for manual deployment
- Ensure `dist` folder contains built files



