# Integrated Application Deployment

## 🎯 New Architecture

### Single Integrated Application
- **One App Service**: FastAPI serves both API and React frontend
- **One URL**: `https://gait-analysis-app.azurewebsites.net`
- **All in West US 3**: Every resource in the same region
- **Microsoft Native**: All Azure managed services

## 📦 Architecture Components

### Application Layer
- **FastAPI Backend**: API endpoints for video analysis
- **React Frontend**: Served as static files by FastAPI
- **Single Container**: Docker image with both frontend and backend

### Azure Services (All in West US 3)
1. **Azure Blob Storage**: Video file storage
2. **Azure Computer Vision**: Video analysis
3. **Azure SQL Database**: Metadata storage
4. **Azure Container Registry**: Docker image storage
5. **Azure App Service**: Hosting (B1 tier)

## 🚀 Deployment Process

The deployment script (`scripts/deploy-integrated-app.sh`) is currently running and will:

1. ✅ Create Resource Group (West US 3)
2. ⏳ Create Azure Services:
   - Blob Storage account
   - Computer Vision resource
   - SQL Database server
3. ⏳ Create App Service Plan (B1, Linux)
4. ⏳ Create App Service
5. ⏳ Create Azure Container Registry
6. ⏳ Build React frontend
7. ⏳ Build Docker image (includes frontend + backend)
8. ⏳ Push image to ACR
9. ⏳ Configure App Service with:
   - Docker container
   - Environment variables
   - Always-On enabled
10. ⏳ Test application

## 🔗 Final Application URL

Once deployment completes:
- **Single URL**: `https://gait-analysis-app.azurewebsites.net`
  - Frontend: `https://gait-analysis-app.azurewebsites.net/`
  - API: `https://gait-analysis-app.azurewebsites.net/api/v1/analysis/...`
  - Health: `https://gait-analysis-app.azurewebsites.net/health`

## ✅ Benefits

1. **Single URL**: Everything accessible from one domain
2. **Simplified**: No CORS issues, no separate frontend/backend URLs
3. **Fast**: All resources in same region (West US 3)
4. **Reliable**: Microsoft managed services
5. **Cost-Effective**: Single App Service plan

## ⏳ Deployment Status

The deployment is currently running in the background. This typically takes:
- Resource creation: 2-3 minutes
- Frontend build: 30 seconds
- Docker build: 2-3 minutes
- Container startup: 1-2 minutes

**Total time: ~5-8 minutes**

## 🧪 Testing

Once deployment completes, test:
```bash
# Health check
curl https://gait-analysis-app.azurewebsites.net/health

# Frontend
curl https://gait-analysis-app.azurewebsites.net/

# API
curl https://gait-analysis-app.azurewebsites.net/api/v1/analysis/upload
```

## 📋 What Was Deleted

All previous resources were deleted:
- Old App Services
- Static Web Apps
- Container Registries
- Storage Accounts
- Cognitive Services
- SQL Databases

## 🎯 Next Steps

1. Wait for deployment to complete (~5-8 minutes)
2. Test the application at the single URL
3. Verify all functionality works
4. Update any documentation with new URL


