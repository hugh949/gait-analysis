# Direct Deployment from Cursor to Azure

## Overview

We now deploy **directly from Cursor to Azure**, bypassing GitHub to avoid conflicts with outdated GitHub code.

## Deployment Methods

### Frontend Deployment

**Quick Deploy:**
```bash
./scripts/deploy-frontend-direct.sh
```

**Manual Steps:**
```bash
cd frontend
npm run build
npx @azure/static-web-apps-cli deploy dist \
  --deployment-token 1aaad346d4e5bd36241348cfca7dde044f070ae22516f876ea34bde2d6f6bcd201-0ab6484a-20a7-49f6-979d-bd3285fc68d000f21100a467810f \
  --env production
```

**Frontend URL:** https://jolly-meadow-0a467810f.1.azurestaticapps.net

### Backend Deployment

**Quick Deploy:**
```bash
./scripts/deploy-backend-direct.sh
```

**Manual Steps:**
```bash
cd backend
az acr build --registry gaitanalysisacreus2 --image gait-analysis-api:latest .
az webapp config container set \
  --name gait-analysis-api-simple \
  --resource-group gait-analysis-rg-eus2 \
  --docker-custom-image-name gaitanalysisacreus2.azurecr.io/gait-analysis-api:latest
az webapp restart --name gait-analysis-api-simple --resource-group gait-analysis-rg-eus2
```

**Backend URL:** https://gait-analysis-api-simple.azurewebsites.net

## Benefits

✅ **No GitHub conflicts** - Deploy local code directly  
✅ **Faster deployment** - No need to push/pull from GitHub  
✅ **Always current** - Deploy exactly what's in Cursor  
✅ **Simple workflow** - One command deployment

## Notes

- Frontend deployments are fast (~30 seconds)
- Backend deployments take longer (~2-3 minutes for Docker build + restart)
- All deployments go directly from local code to Azure
- GitHub is no longer part of the deployment pipeline

