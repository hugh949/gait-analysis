# Testing Guide - Gait Analysis Application

## ✅ Application Status

### Backend API (Deployed & Running)
- **URL**: https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io
- **Status**: ✅ Healthy
- **Location**: East US 2

### Frontend (Ready for Deployment)
- **Built**: ✅ `frontend/dist/` contains production build
- **Static Web App**: `gait-analysis-web`
- **URL**: https://gentle-wave-0d4e1d10f.4.azurestaticapps.net
- **API URL Configured**: ✅ Points to backend

## 🚀 Quick Start Testing

### Option 1: Test Backend Directly

#### Health Check
```bash
curl https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/health
```

Expected response:
```json
{"status":"healthy","components":{"database":"connected","ml_models":"loaded","quality_gate":"active"}}
```

#### Test API Root
```bash
curl https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/
```

#### Upload Video (Test Endpoint)
```bash
curl -X POST \
  https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/api/v1/analysis/upload \
  -F "file=@/path/to/test-video.mp4" \
  -F "view_type=front"
```

### Option 2: Deploy Frontend & Test Full Application

#### Step 1: Get Deployment Token

**Via Azure Portal:**
1. Go to https://portal.azure.com
2. Navigate to: Resource Groups → `gait-analysis-rg` → `gait-analysis-web`
3. Click "Manage deployment token" in the left menu
4. Copy the deployment token

**Via Azure CLI:**
```bash
az rest --method post \
  --uri "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/gait-analysis-rg/providers/Microsoft.Web/staticSites/gait-analysis-web/listSecrets?api-version=2022-03-01" \
  --query "properties.apiKey" -o tsv
```

#### Step 2: Deploy Frontend

**Using SWA CLI:**
```bash
cd frontend
npm install -g @azure/static-web-apps-cli
swa deploy ./dist --deployment-token <your-token> --env production
```

**Using Azure Portal:**
1. Go to Static Web App in Azure Portal
2. Navigate to "Overview" → "Browse"
3. Or use "Deployment Center" to connect to GitHub for automatic deployments

#### Step 3: Test Frontend

1. Open: https://gentle-wave-0d4e1d10f.4.azurestaticapps.net
2. Navigate to "Upload Video"
3. Upload a test video file
4. Wait for analysis to complete
5. View results in the appropriate dashboard:
   - Medical Dashboard
   - Caregiver Dashboard
   - Older Adult Dashboard

## 📋 Test Scenarios

### 1. Backend Health Check
- **Endpoint**: `GET /health`
- **Expected**: 200 OK with health status
- **Test**: `curl https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/health`

### 2. Video Upload
- **Endpoint**: `POST /api/v1/analysis/upload`
- **Test**: Upload a video file (MP4, AVI, MOV, MKV)
- **Expected**: Returns analysis ID and "processing" status

### 3. Get Analysis Status
- **Endpoint**: `GET /api/v1/analysis/{analysis_id}`
- **Test**: Check status of uploaded analysis
- **Expected**: Returns status (processing/completed/failed) and metrics if completed

### 4. Get Reports
- **Endpoint**: `GET /api/v1/reports/{analysis_id}?audience={medical|caregiver|older_adult}`
- **Test**: Retrieve reports for different audiences
- **Expected**: Returns audience-specific report with metrics

### 5. Frontend Integration
- **Test**: Full workflow through frontend UI
- **Steps**:
  1. Upload video
  2. Wait for processing
  3. View results in dashboards
  4. Verify all three audience views work

## 🔧 Troubleshooting

### Backend Issues

**Check Container App Logs:**
```bash
az containerapp logs show \
  --name gait-analysis-api-wus3 \
  --resource-group gait-analysis-rg-wus3 \
  --follow
```

**Check Container App Status:**
```bash
az containerapp show \
  --name gait-analysis-api-wus3 \
  --resource-group gait-analysis-rg-wus3 \
  --query properties.runningStatus
```

**Restart Container App:**
```bash
az containerapp revision restart \
  --name gait-analysis-api-wus3 \
  --resource-group gait-analysis-rg-wus3
```

### Frontend Issues

**Check Static Web App Logs:**
- Azure Portal → Static Web App → Monitoring → Log stream

**Verify API URL:**
- Check browser console for API connection errors
- Verify `VITE_API_URL` is set correctly in build

**Rebuild Frontend:**
```bash
cd frontend
VITE_API_URL=https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io npm run build
```

## 📊 Monitoring

### Container App Metrics
- Azure Portal → Container App → Metrics
- Monitor: CPU, Memory, Requests, Response Time

### Static Web App Metrics
- Azure Portal → Static Web App → Metrics
- Monitor: Requests, Response Time, Errors

### Cosmos DB Metrics
- Azure Portal → Cosmos DB → Metrics
- Monitor: Request Units, Storage, Latency

## ✅ Success Criteria

Application is working correctly if:
1. ✅ Backend health check returns healthy status
2. ✅ Video upload accepts files and returns analysis ID
3. ✅ Analysis completes and returns metrics
4. ✅ Reports are generated for all three audiences
5. ✅ Frontend displays results correctly
6. ✅ All dashboards load and show data

## 🎯 Next Steps After Testing

1. **Performance Testing**: Test with various video sizes and formats
2. **Load Testing**: Test concurrent uploads
3. **Error Handling**: Test with invalid files, network issues
4. **UI/UX Testing**: Verify all user flows work smoothly
5. **Integration Testing**: Test end-to-end workflows

## 📞 Support

If you encounter issues:
1. Check logs (see Troubleshooting section)
2. Verify all resources are running
3. Check network connectivity
4. Review error messages in browser console (F12)



