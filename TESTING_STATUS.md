# Testing Status & Instructions

## ✅ Application Status

### Frontend
- **URL**: https://gentle-wave-0d4e1d10f.4.azurestaticapps.net
- **Status**: ✅ Deployed and accessible
- **Location**: East US 2

### Backend
- **URL**: https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io
- **Status**: ✅ Running (updating image)
- **Location**: East US 2
- **Note**: Container scales from zero (first request takes 30-60 seconds)

---

## 🧪 How to Test Right Now

### Quick Test (Web Browser)

1. **Open**: https://gentle-wave-0d4e1d10f.4.azurestaticapps.net

2. **Upload Video**:
   - Click "Upload Video"
   - Select a video file
   - Click "Upload and Analyze"
   - ⚠️ **Wait 30-60 seconds** for first request (container startup)

3. **If Upload Fails**:
   - Check browser console (F12) for errors
   - Wait 30-60 seconds and try again
   - The container may be starting up

---

### Test Backend API

#### Health Check (Wake up container)
```bash
curl https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/health
```
**Wait 30-60 seconds** for first response (container starting)

#### Upload Video
```bash
curl -X POST \
  https://gait-analysis-api-wus3.jollymeadow-b5f64007.eastus2.azurecontainerapps.io/api/v1/analysis/upload \
  -F "file=@your-video.mp4" \
  -F "view_type=front"
```

---

## ⚠️ Known Issues

### Container App Image Update
- Currently updating from old ACR to new ACR (East US 2)
- Update may take a few minutes
- Container app is still functional with old image

### Container Scaling
- **Min Replicas: 0** (scales to zero when idle)
- First request after idle: **30-60 seconds**
- This is normal behavior for cost optimization

### If Commands Hang
- Container app updates can take 2-5 minutes
- If command hangs > 5 minutes, cancel and check status
- Use `az containerapp show` to verify current state

---

## 🔍 Check Current Status

### Check Container App
```bash
az containerapp show \
  --name gait-analysis-api-wus3 \
  --resource-group gait-analysis-rg-wus3 \
  --query "{image:properties.template.containers[0].image,status:properties.runningStatus}"
```

### Check Revisions
```bash
az containerapp revision list \
  --name gait-analysis-api-wus3 \
  --resource-group gait-analysis-rg-wus3 \
  --output table
```

### Check Logs
```bash
az containerapp logs show \
  --name gait-analysis-api-wus3 \
  --resource-group gait-analysis-rg-wus3 \
  --tail 20
```

---

## ✅ Testing Checklist

- [ ] Frontend loads: https://gentle-wave-0d4e1d10f.4.azurestaticapps.net
- [ ] Can navigate pages
- [ ] Upload page accessible
- [ ] Backend responds (may take 30-60s first time)
- [ ] Can upload video file
- [ ] Analysis ID returned
- [ ] Can view results in dashboards

---

## 🚀 Ready to Test!

**Start here**: https://gentle-wave-0d4e1d10f.4.azurestaticapps.net

**Remember**: First request takes 30-60 seconds (container startup)

The application is ready for testing! 🎉



