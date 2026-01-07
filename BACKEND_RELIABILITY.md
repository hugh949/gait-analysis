# Backend Reliability Issues & Solutions

## Current Status

✅ **Always-On**: Enabled  
✅ **App Service Plan**: Basic B1 (supports Always-On)  
⚠️ **Application**: Crashing/Returning 503 errors

## Root Causes

1. **Application Crashes**: Container may be crashing on startup
2. **No Health Check**: Azure doesn't know when app is unhealthy
3. **No Auto-Heal**: App doesn't automatically restart on failure
4. **Startup Issues**: Application may fail during initialization

## Solutions Applied

### 1. Health Check Path
- Set health check path to `/` endpoint
- Azure will ping this endpoint to check if app is healthy
- If unhealthy, Azure will restart the app

### 2. Auto-Heal
- Enable auto-heal to automatically restart on failures
- Configure restart rules based on HTTP status codes

### 3. Application Improvements Needed

**Add better error handling in startup:**
```python
# In main.py lifespan
try:
    await init_db()
    logger.info("Database initialized")
except Exception as e:
    logger.error(f"Database initialization failed: {e}")
    # Don't crash - continue with degraded mode
```

**Add startup health check:**
```python
@app.get("/startup")
async def startup_check():
    """Check if app is ready"""
    try:
        # Check critical services
        await db.get_container("analyses")
        return {"status": "ready"}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}
```

## Monitoring

**Check backend status:**
```bash
curl https://gait-analysis-api-simple.azurewebsites.net/
```

**View logs:**
```bash
az webapp log tail --name gait-analysis-api-simple --resource-group gait-analysis-rg-wus3
```

**Restart backend:**
```bash
az webapp restart --name gait-analysis-api-simple --resource-group gait-analysis-rg-wus3
```

## Next Steps

1. ✅ Enable health check path
2. ✅ Enable auto-heal
3. ⏳ Improve application error handling
4. ⏳ Add startup health checks
5. ⏳ Monitor and fix root cause of crashes

## Why Backend Stops

**Common Reasons:**
- **Memory limits**: B1 has 1.75GB RAM - large video processing may exceed
- **Startup failures**: Database connection, missing env vars, etc.
- **Container crashes**: Unhandled exceptions in application code
- **Timeout issues**: Long-running operations exceeding limits

**Solutions:**
- Upgrade to B2 or higher for more memory
- Add comprehensive error handling
- Use background tasks for long operations
- Implement graceful degradation



