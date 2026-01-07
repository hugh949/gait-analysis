# 📚 Deployment Lessons Learned - Don't Repeat These Mistakes

## Critical Issues We've Fixed

### 1. ✅ macOS Compatibility
**Problem**: `timeout` command not available on macOS by default  
**Solution**: Added custom timeout function to all scripts  
**Status**: Fixed in all deployment scripts

### 2. ✅ Azure CLI Commands Hanging
**Problem**: Azure CLI commands can hang indefinitely (especially `az webapp deployment source sync`)  
**Solution**: Added timeouts to ALL Azure CLI commands (30-60 seconds)  
**Status**: All scripts now have timeouts

### 3. ✅ grep -oP Not Working on macOS
**Problem**: macOS grep doesn't support `-P` flag (Perl regex)  
**Solution**: Replaced with `sed` commands  
**Status**: Fixed in all scripts

### 4. ✅ CORS Configuration
**Problem**: Frontend can't communicate with backend without proper CORS  
**Solution**: 
- Use `config_simple.py` (no pydantic issues)
- Set `CORS_ORIGINS` environment variable
- Include frontend URL: `https://jolly-meadow-0a467810f.1.azurestaticapps.net`
**Status**: Fixed in deployment scripts

### 5. ✅ Always-On Configuration
**Problem**: Backend stops responding when not in use  
**Solution**: Enable Always-On in App Service settings  
**Status**: Included in deployment scripts

### 6. ✅ Native Python Deployment Issues
**Problem**: ZIP deployments don't trigger Oryx builds automatically  
**Problem**: Dependencies (torch) aren't installed  
**Solution**: **Use Docker deployment instead** - it includes all dependencies  
**Status**: Docker deployment is the recommended method

### 7. ✅ Progress Updates
**Problem**: Long-running operations with no feedback  
**Solution**: Added progress messages every 10 seconds  
**Status**: All scripts have progress updates

### 8. ✅ Health Check Endpoint
**Problem**: Using root `/` endpoint for health checks is unreliable  
**Solution**: Use `/health` endpoint which is more reliable  
**Status**: Updated in all scripts

### 9. ✅ Error Handling
**Problem**: Scripts fail completely on any error  
**Solution**: Added `|| true` and error handling to continue on non-critical failures  
**Status**: Improved error handling throughout

## Current Working Solution

### ✅ Docker Deployment (Recommended)
**Why it works:**
- Docker builds include ALL dependencies (torch, uvicorn, everything)
- No Oryx build issues
- Proven to work
- One command deployment

**Script**: `scripts/deploy-backend-direct.sh`
- ✅ Includes all fixes above
- ✅ macOS compatible
- ✅ Timeouts on all commands
- ✅ CORS configuration
- ✅ Always-On enabled
- ✅ Progress updates
- ✅ Proper health checks

### ❌ Native Python Deployment (Not Recommended)
**Why it doesn't work:**
- ZIP deployments don't trigger Oryx builds
- Dependencies aren't installed
- Complex workarounds needed
- Unreliable

## Deployment Checklist

Before deploying, ensure:
- [ ] Using Docker deployment (not native Python)
- [ ] Script has timeout function (macOS compatibility)
- [ ] All Azure CLI commands have timeouts
- [ ] CORS_ORIGINS is set correctly
- [ ] Always-On is enabled
- [ ] Health check uses `/health` endpoint
- [ ] Progress updates are included

## Quick Reference

**Deploy Backend (Docker - Recommended):**
```bash
bash scripts/deploy-backend-direct.sh
```

**Check Backend Health:**
```bash
curl https://gait-analysis-api-simple.azurewebsites.net/health
```

**View Logs:**
```bash
az webapp log tail --name gait-analysis-api-simple --resource-group gait-analysis-rg-wus3
```

**Frontend URL:**
```
https://jolly-meadow-0a467810f.1.azurestaticapps.net
```

**Backend URL:**
```
https://gait-analysis-api-simple.azurewebsites.net
```

## Key Takeaways

1. **Always use Docker deployment** for backend (includes all dependencies)
2. **Always add timeouts** to Azure CLI commands (they can hang)
3. **Always configure CORS** (frontend needs it)
4. **Always enable Always-On** (backend reliability)
5. **Always use `/health` endpoint** for health checks
6. **Always test on macOS** (different from Linux)


