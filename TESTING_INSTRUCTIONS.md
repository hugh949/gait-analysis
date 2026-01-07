# Testing Instructions - Gait Analysis App

## ✅ Application Status

- **Frontend**: ✅ Accessible at https://gentle-wave-0d4e1d10f.4.azurestaticapps.net
- **Backend**: ✅ Configured (scales from zero - first request takes 30-60 seconds)
- **All Resources**: ✅ Deployed to East US 2 only

---

## 🧪 How to Test

### Method 1: Web Browser (Recommended)

1. **Open the Application**
   ```
   https://gentle-wave-0d4e1d10f.4.azurestaticapps.net
   ```

2. **Upload a Video**
   - Click "Upload Video" or "Start Analysis"
   - Select a video file (MP4, AVI, MOV, or MKV)
   - Click "Upload and Analyze"
   - ⚠️ **Wait 30-60 seconds** - The backend container is starting
   - You should see an Analysis ID when it's ready

3. **View Results**
   - Copy the Analysis ID
   - Navigate to any dashboard (Medical/Caregiver/Older Adult)
   - Enter the Analysis ID
   - View the results

---

### Method 2: Command Line API Testing

#### Step 1: Wake Up the Backend (Wait 30-60 seconds)
```bash
curl https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/health
```

**Expected**: After 30-60 seconds, returns:
```json
{"status":"healthy","components":{"database":"connected",...}}
```

#### Step 2: Upload a Video
```bash
curl -X POST \
  https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/api/v1/analysis/upload \
  -F "file=@/path/to/your/video.mp4" \
  -F "view_type=front"
```

**Expected**: Returns analysis ID:
```json
{"analysis_id":"...","status":"processing","message":"..."}
```

#### Step 3: Check Analysis Status
```bash
# Replace {analysis_id} with ID from step 2
curl https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/api/v1/analysis/{analysis_id}
```

---

## ⚠️ Important: Container Scaling

### Current Configuration
- **Min Replicas: 0** (scales to zero when idle)
- **First Request**: Takes 30-60 seconds (container startup)
- **Subsequent Requests**: Fast (< 1 second)

### Why the Delay?
1. Container App scales to zero to save costs
2. First request triggers container startup
3. Container pulls image and starts application
4. This takes 30-60 seconds

### Options

**Option A: Wait for First Request** (Recommended for Testing)
- Just wait 30-60 seconds on first request
- Subsequent requests are fast
- No additional cost

**Option B: Keep Container Running** (Faster, but costs more)
```bash
az containerapp update \
  --name gait-analysis-api-wus3 \
  --resource-group gait-analysis-rg-wus3 \
  --min-replicas 1
```
This keeps 1 container always running (faster, but costs ~$0.000012/second)

---

## 🔍 Troubleshooting

### If Upload Fails in Browser

1. **Check Browser Console** (Press F12)
   - Look for errors in Console tab
   - Check Network tab for failed requests
   - Look for CORS errors

2. **Wait Longer**
   - First request can take up to 60 seconds
   - Be patient - container is starting

3. **Check Backend Logs**
   ```bash
   az containerapp logs show \
     --name gait-analysis-api-wus3 \
     --resource-group gait-analysis-rg-wus3 \
     --tail 50
   ```

### If Backend Times Out

- This is **normal** for first request
- Wait 30-60 seconds and try again
- Or increase min replicas (see Option B above)

---

## ✅ Testing Checklist

- [ ] Frontend loads: https://gentle-wave-0d4e1d10f.4.azurestaticapps.net
- [ ] Can navigate between pages
- [ ] Upload page accessible
- [ ] Can select video file
- [ ] Upload button works
- [ ] Wait 30-60 seconds for first request
- [ ] Analysis ID is returned
- [ ] Can view results in dashboards

---

## 🚀 Start Testing Now!

**Frontend URL**: https://gentle-wave-0d4e1d10f.4.azurestaticapps.net

**Remember**: 
- First request takes **30-60 seconds** ⏱️
- This is normal - container is starting
- Subsequent requests are fast

The application is **ready for testing**! 🎉

---

## Quick Test Commands

```bash
# Test script
./test-app.sh

# Wake up backend (wait 30-60s)
curl https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/health

# Check container status
az containerapp show \
  --name gait-analysis-api-wus3 \
  --resource-group gait-analysis-rg-wus3 \
  --query properties.runningStatus
```



