# 🔧 Dashboard Error Troubleshooting

## Error: "Failed to fetch analysis:"

This error occurs when the dashboard cannot retrieve analysis data from the backend API.

## Improved Error Handling

✅ **Latest Update**: Error handling has been improved to show more detailed error messages including:
- HTTP status codes
- Actual error text from API
- Console logging for debugging

## Common Causes & Solutions

### 1. Analysis ID Not Found (404)

**Symptoms**:
- Error message: "Failed to fetch analysis (404): Analysis not found"
- Dashboard shows error

**Solutions**:
- Verify the analysis ID is correct
- Check if analysis exists in the database
- Make sure you're using a valid analysis ID from a completed upload

**Check**:
```bash
# Test API endpoint (replace {analysis_id} with actual ID)
curl https://gait-analysis-api-simple.azurewebsites.net/api/v1/analysis/{analysis_id}
```

### 2. Analysis Still Processing

**Symptoms**:
- Error message: "Failed to fetch analysis (400): Analysis not completed"
- Analysis status is "processing"

**Solutions**:
- Wait for analysis to complete (usually 2-5 minutes)
- Click "Refresh Status" button
- Check backend logs for processing status

**Check Status**:
```bash
curl https://gait-analysis-api-simple.azurewebsites.net/api/v1/analysis/{analysis_id}
```

### 3. CORS Errors

**Symptoms**:
- Error in browser console: "CORS policy" or "No 'Access-Control-Allow-Origin' header"
- Network tab shows CORS errors

**Solutions**:
- Check backend CORS configuration
- Verify frontend URL is allowed in backend CORS settings
- Check backend logs for CORS errors

**Backend CORS Config**:
- Frontend URL: `https://jolly-meadow-0a467810f.1.azurestaticapps.net`
- Should be allowed in backend CORS configuration

### 4. Network/Connection Errors

**Symptoms**:
- Error message: "Failed to fetch analysis: Network error"
- Connection timeout

**Solutions**:
- Check backend is online: https://gait-analysis-api-simple.azurewebsites.net/
- Verify API URL is correct
- Check network connectivity
- Verify backend "Always-On" is enabled

**Test Backend**:
```bash
curl https://gait-analysis-api-simple.azurewebsites.net/
# Should return: {"status":"healthy","service":"Gait Analysis API","version":"1.0.0"}
```

### 5. Invalid Analysis ID Format

**Symptoms**:
- Error message: "Failed to fetch analysis (400): Invalid format"
- Analysis ID doesn't match expected format

**Solutions**:
- Use analysis ID from upload response
- Analysis ID should be a UUID format
- Check URL parameter format: `?analysisId={id}`

## Debugging Steps

### Step 1: Check Browser Console

1. Open browser DevTools (F12)
2. Go to Console tab
3. Look for error messages and logs
4. Check for:
   - Fetch URL
   - Response status
   - Error details

### Step 2: Check Network Tab

1. Open browser DevTools (F12)
2. Go to Network tab
3. Reload the dashboard
4. Find the API request to `/api/v1/analysis/{id}`
5. Check:
   - Request URL
   - Response status
   - Response body
   - Headers

### Step 3: Test API Directly

Test the API endpoint directly:

```bash
# Replace {analysis_id} with your actual analysis ID
curl https://gait-analysis-api-simple.azurewebsites.net/api/v1/analysis/{analysis_id}
```

**Expected Response** (completed):
```json
{
  "analysis_id": "...",
  "status": "completed",
  "metrics": {
    "cadence": 120,
    "step_length": 0.5,
    ...
  }
}
```

**Expected Response** (processing):
```json
{
  "analysis_id": "...",
  "status": "processing",
  "message": "Analysis in progress"
}
```

**Expected Response** (not found):
```json
{
  "detail": "Analysis not found"
}
```

### Step 4: Verify Analysis ID

1. Get analysis ID from upload success message
2. Verify it's a valid UUID format
3. Check if it exists in the database

### Step 5: Check Backend Logs

Check backend logs for errors:

```bash
az webapp log tail --name gait-analysis-api-simple --resource-group gait-analysis-rg-wus3
```

Look for:
- Analysis retrieval errors
- Database connection errors
- Processing errors

## Quick Fixes

### Fix 1: Wait for Processing

If analysis is still processing:
- Wait 2-5 minutes
- Click "Refresh Status" button
- Analysis needs to complete before results are available

### Fix 2: Verify Analysis ID

If you're manually entering analysis ID:
- Copy it exactly from upload response
- Make sure URL format is: `?analysisId={id}` (no spaces, correct capitalization)

### Fix 3: Check Backend Status

If getting connection errors:
- Verify backend is online
- Check "Always-On" is enabled
- Wait 30-60 seconds for backend to start (if it was idle)

### Fix 4: Clear Browser Cache

If getting cached errors:
- Clear browser cache
- Hard refresh (Ctrl+Shift+R or Cmd+Shift+R)
- Try in incognito/private window

## Improved Error Messages

The dashboard now shows:
- HTTP status codes (404, 400, 500, etc.)
- Actual error text from API
- More helpful error messages
- Console logging for debugging

**Example Error Messages**:
- `Failed to fetch analysis (404): Analysis not found` - Analysis ID doesn't exist
- `Failed to fetch analysis (400): Analysis not completed. Status: processing` - Still processing
- `Failed to fetch analysis: Network error` - Connection issue
- `Failed to fetch analysis (500): Internal server error` - Backend error

## Summary

✅ **Error Handling**: Improved with detailed messages
✅ **Debugging**: Console logging added
✅ **User Messages**: More helpful error messages
✅ **Status Codes**: HTTP status codes shown

**Next Step**: Check browser console (F12) for detailed error information to diagnose the specific issue.



