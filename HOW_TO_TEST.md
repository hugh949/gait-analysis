# How to Test the Gait Analysis Application

## 🌐 Application URLs

### Frontend (Main Application)
**https://gentle-wave-0d4e1d10f.4.azurestaticapps.net**

### Backend API
**https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io**

---

## 🧪 Testing Methods

### Method 1: Test via Web Browser (Easiest)

1. **Open the Frontend**
   - Go to: https://gentle-wave-0d4e1d10f.4.azurestaticapps.net
   - You should see the home page

2. **Test Video Upload**
   - Click "Upload Video" or "Start Analysis"
   - Select a video file (MP4, AVI, MOV, or MKV)
   - Click "Upload and Analyze"
   - Wait for the analysis to process
   - Note the Analysis ID that appears

3. **View Results**
   - Use the Analysis ID to view results in different dashboards:
     - **Medical Dashboard**: Technical details
     - **Caregiver Dashboard**: Fall risk indicator
     - **Older Adult Dashboard**: Health score

---

### Method 2: Test Backend API Directly (Using curl)

#### 1. Health Check
```bash
curl https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "components": {
    "database": "connected",
    "ml_models": "loaded",
    "quality_gate": "active"
  }
}
```

#### 2. Test Root Endpoint
```bash
curl https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/
```

#### 3. Upload a Video
```bash
curl -X POST \
  https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/api/v1/analysis/upload \
  -F "file=@/path/to/your/video.mp4" \
  -F "view_type=front"
```

**Expected Response:**
```json
{
  "analysis_id": "uuid-here",
  "status": "processing",
  "message": "Video uploaded successfully. Analysis in progress."
}
```

#### 4. Check Analysis Status
```bash
# Replace {analysis_id} with the ID from step 3
curl https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/api/v1/analysis/{analysis_id}
```

#### 5. Get Reports
```bash
# Medical report
curl "https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/api/v1/reports/{analysis_id}?audience=medical"

# Caregiver report
curl "https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/api/v1/reports/{analysis_id}?audience=caregiver"

# Older adult report
curl "https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/api/v1/reports/{analysis_id}?audience=older_adult"
```

---

### Method 3: Test Using Postman or Similar Tool

1. **Import Collection** (create these requests):

   - **GET** `https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/health`
   
   - **POST** `https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/api/v1/analysis/upload`
     - Body Type: `form-data`
     - Key: `file` (type: File)
     - Key: `view_type` (type: Text, value: `front`)
   
   - **GET** `https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/api/v1/analysis/{analysis_id}`
   
   - **GET** `https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/api/v1/reports/{analysis_id}?audience=medical`

---

## ✅ Testing Checklist

### Backend API Tests
- [ ] Health check returns "healthy"
- [ ] Root endpoint responds
- [ ] Can upload a video file
- [ ] Analysis ID is returned
- [ ] Can check analysis status
- [ ] Can retrieve reports for all audiences
- [ ] CORS allows frontend requests

### Frontend Tests
- [ ] Home page loads
- [ ] Can navigate to Upload page
- [ ] Can select and upload a video file
- [ ] Upload shows progress/status
- [ ] Can view results in Medical dashboard
- [ ] Can view results in Caregiver dashboard
- [ ] Can view results in Older Adult dashboard

### Integration Tests
- [ ] Frontend can communicate with backend
- [ ] Video upload works end-to-end
- [ ] Analysis completes successfully
- [ ] Reports are generated correctly
- [ ] All three audience views display data

---

## 🔍 Troubleshooting

### If Upload Fails

1. **Check Browser Console** (F12)
   - Look for CORS errors
   - Check network tab for failed requests

2. **Check Backend Logs**
   ```bash
   az containerapp logs show \
     --name gait-analysis-api-wus3 \
     --resource-group gait-analysis-rg-wus3 \
     --tail 50
   ```

3. **Verify CORS Configuration**
   ```bash
   az containerapp show \
     --name gait-analysis-api-wus3 \
     --resource-group gait-analysis-rg-wus3 \
     --query "properties.template.containers[0].env[?name=='CORS_ORIGINS']"
   ```

### If Backend is Not Responding

1. **Check Container App Status**
   ```bash
   az containerapp show \
     --name gait-analysis-api-wus3 \
     --resource-group gait-analysis-rg-wus3 \
     --query properties.runningStatus
   ```

2. **Check if Container is Running**
   ```bash
   az containerapp revision list \
     --name gait-analysis-api-wus3 \
     --resource-group gait-analysis-rg-wus3 \
     --query "[0].properties.activeState"
   ```

3. **Restart Container App** (if needed)
   ```bash
   az containerapp revision restart \
     --name gait-analysis-api-wus3 \
     --resource-group gait-analysis-rg-wus3 \
     --revision gait-analysis-api-wus3--latest
   ```

---

## 📊 Quick Test Script

Save this as `test-app.sh`:

```bash
#!/bin/bash

API_URL="https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io"

echo "Testing Gait Analysis API..."
echo ""

echo "1. Health Check:"
curl -s "$API_URL/health" | jq .
echo ""

echo "2. Root Endpoint:"
curl -s "$API_URL/" | jq .
echo ""

echo "3. Testing CORS (OPTIONS request):"
curl -X OPTIONS \
  -H "Origin: https://gentle-wave-0d4e1d10f.4.azurestaticapps.net" \
  -H "Access-Control-Request-Method: POST" \
  -v "$API_URL/api/v1/analysis/upload" 2>&1 | grep -E "(HTTP|Access-Control)"
echo ""

echo "✅ Basic tests complete!"
echo ""
echo "To test upload, use:"
echo "curl -X POST $API_URL/api/v1/analysis/upload -F 'file=@your-video.mp4' -F 'view_type=front'"
```

Run with: `chmod +x test-app.sh && ./test-app.sh`

---

## 🎯 Expected Test Results

### Successful Test Flow

1. **Health Check**: Returns `{"status": "healthy", ...}`
2. **Upload**: Returns `{"analysis_id": "...", "status": "processing"}`
3. **Status Check**: Returns `{"status": "completed", "metrics": {...}}`
4. **Reports**: Returns audience-specific reports with metrics

### Common Issues

- **CORS Error**: Backend not allowing frontend origin
- **Timeout**: Container App scaled to zero (first request may be slow)
- **Upload Fails**: Check file size (max 500MB) and format
- **Analysis Fails**: Check backend logs for processing errors

---

## 📝 Test Video Requirements

For testing, use a video that:
- Format: MP4, AVI, MOV, or MKV
- Size: Under 500MB
- Content: Shows a person walking (for realistic testing)
- Duration: 10-60 seconds is ideal

---

## 🚀 Ready to Test!

1. **Start with the frontend**: https://gentle-wave-0d4e1d10f.4.azurestaticapps.net
2. **Or test the API directly** using the curl commands above
3. **Check logs** if anything fails

The application is ready for testing! 🎉



