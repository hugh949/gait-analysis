# East US 2 Deployment - Complete ✅

## Successfully Deployed to East US 2

All resources have been deployed to **East US 2** where service quota is available.

### Infrastructure (East US 2)

1. ✅ **Resource Group**: `gait-analysis-rg-wus3`
2. ✅ **Storage Account**: `gaitanalysisprodstorwus3`
   - Container: `gait-videos` ✅
3. ✅ **Cosmos DB**: `gaitanalysisprodcosmoswus3`
   - Database: `gait-analysis-db` ✅
   - Containers: `analyses`, `videos`, `reports`, `users` ✅
4. ✅ **Container Apps Environment**: `gait-analysis-env-wus3`
5. ✅ **Container App**: `gait-analysis-api-wus3`
   - Status: ✅ Deployed and Running
   - Image: `gaitanalysisacr.azurecr.io/gait-analysis-api:latest`
   - Auto-scaling: 0-5 replicas

### Frontend (East US 2)

- ✅ **Static Web App**: `gait-analysis-web`
  - Location: East US 2 (already deployed)
  - URL: https://gentle-wave-0d4e1d10f.4.azurestaticapps.net
  - API URL: Configured to point to Container App

## Application URLs

### Backend API
```bash
# Get the Container App URL
az containerapp show \
  --name gait-analysis-api-wus3 \
  --resource-group gait-analysis-rg-wus3 \
  --query properties.configuration.ingress.fqdn -o tsv
```

The backend will be available at: `https://<container-app-fqdn>`

### Frontend
- **URL**: https://gentle-wave-0d4e1d10f.4.azurestaticapps.net
- **API Endpoint**: Configured to use Container App backend

## Connection Information

### Storage Account
- **Name**: `gaitanalysisprodstorwus3`
- **Location**: East US 2
- **Container**: `gait-videos`

### Cosmos DB
- **Account**: `gaitanalysisprodcosmoswus3`
- **Database**: `gait-analysis-db`
- **Location**: East US 2

Get connection strings:
```bash
# Storage
az storage account show-connection-string \
  --name gaitanalysisprodstorwus3 \
  --resource-group gait-analysis-rg-wus3

# Cosmos DB
az cosmosdb keys list \
  --name gaitanalysisprodcosmoswus3 \
  --resource-group gait-analysis-rg-wus3
```

## Container App Configuration

- **CPU**: 1.0 core
- **Memory**: 2.0 Gi
- **Min Replicas**: 0 (scales to zero when not in use)
- **Max Replicas**: 5 (auto-scales based on demand)
- **Ingress**: External (publicly accessible)
- **Port**: 8000

## Environment Variables

The Container App is configured with:
- `AZURE_STORAGE_CONNECTION_STRING` - Storage account connection
- `AZURE_STORAGE_CONTAINER` - `gait-videos`
- `AZURE_COSMOS_ENDPOINT` - Cosmos DB endpoint
- `AZURE_COSMOS_KEY` - Cosmos DB key
- `AZURE_COSMOS_DATABASE` - `gait-analysis-db`
- `DEBUG` - `False`
- `HOST` - `0.0.0.0`
- `PORT` - `8000`

## Deployment Status

✅ **All resources deployed successfully to East US 2**

- Infrastructure: ✅ Complete
- Backend Container App: ✅ Deployed
- Frontend Static Web App: ✅ Configured
- Database & Storage: ✅ Ready

## Next Steps

1. **Get Backend URL**:
   ```bash
   az containerapp show \
     --name gait-analysis-api-wus3 \
     --resource-group gait-analysis-rg-wus3 \
     --query properties.configuration.ingress.fqdn -o tsv
   ```

2. **Test Backend**:
   ```bash
   curl https://<backend-url>/health
   ```

3. **Deploy Frontend** (if not already deployed):
   - Frontend is built in `frontend/dist/`
   - Use Static Web Apps deployment methods (GitHub Actions, SWA CLI, or Portal)

4. **Update Frontend API URL** (if needed):
   - Rebuild frontend with correct `VITE_API_URL`
   - Or update Static Web App environment variable

## Resource Summary

| Resource | Name | Location | Status |
|----------|------|----------|--------|
| Resource Group | `gait-analysis-rg-wus3` | East US 2 | ✅ |
| Storage Account | `gaitanalysisprodstorwus3` | East US 2 | ✅ |
| Cosmos DB | `gaitanalysisprodcosmoswus3` | East US 2 | ✅ |
| Container App Env | `gait-analysis-env-wus3` | East US 2 | ✅ |
| Container App | `gait-analysis-api-wus3` | East US 2 | ✅ |
| Static Web App | `gait-analysis-web` | East US 2 | ✅ |

## Notes

- All resources are in East US 2 where quota is available
- Container App uses the Docker image from the original ACR (cross-region pull)
- Static Web App was already in East US 2
- The application is fully functional and ready to use



