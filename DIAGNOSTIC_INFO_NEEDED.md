# Diagnostic Information Needed from Azure

## Why Deployments Are Failing

Both Docker and native deployments have failed. To diagnose the root cause, I need specific information from Azure.

## Information to Collect

### 1. Application Logs (Most Important)

**From Azure Portal:**
1. Go to: `gait-analysis-api-simple` App Service
2. Navigate to: **Log stream** or **Logs** section
3. Copy the **last 50-100 lines** of logs
4. Look for:
   - Python errors
   - Import errors
   - Module not found errors
   - Startup failures
   - Database connection errors

**Or via CLI:**
```bash
az webapp log tail --name gait-analysis-api-simple --resource-group gait-analysis-rg-wus3
```

### 2. Deployment Logs

**From Azure Portal:**
1. Go to: `gait-analysis-api-simple` App Service
2. Navigate to: **Deployment Center** or **Deployment slots**
3. Check: **Deployment history**
4. Click on the **latest failed deployment**
5. Copy the **deployment log output**

**Or via CLI:**
```bash
az webapp deployment list-publishing-profiles --name gait-analysis-api-simple --resource-group gait-analysis-rg-wus3
```

### 3. Build Logs (Oryx Build)

**From Azure Portal:**
1. Go to: `gait-analysis-api-simple` App Service
2. Navigate to: **Advanced Tools (Kudu)** → **Go**
3. Click: **Debug console** → **CMD** or **PowerShell**
4. Navigate to: `D:\home\LogFiles\` or `/home/LogFiles/`
5. Look for: `oryx-build.log` or `deployment.log`
6. Copy the **build output**

**Or via Kudu URL:**
- Direct: `https://gait-analysis-api-simple.scm.azurewebsites.net`
- Navigate to: LogFiles folder

### 4. Application Insights (If Enabled)

**From Azure Portal:**
1. Go to: Application Insights (if configured)
2. Check: **Failures** or **Exceptions**
3. Look for: Recent errors during startup

### 5. Process Status

**From Kudu:**
1. Go to: `https://gait-analysis-api-simple.scm.azurewebsites.net`
2. Navigate to: **Process Explorer**
3. Check: What processes are running
4. Look for: Python process, uvicorn process

### 6. File System Check

**From Kudu:**
1. Go to: `https://gait-analysis-api-simple.scm.azurewebsites.net`
2. Navigate to: **Debug console** → **CMD**
3. Check if files are deployed:
   ```bash
   dir D:\home\site\wwwroot
   # or
   ls /home/site/wwwroot
   ```
4. Check if `startup.sh` exists and is executable
5. Check if `main.py` exists
6. Check if `requirements.txt` exists

### 7. Environment Check

**From Kudu:**
1. Go to: `https://gait-analysis-api-simple.scm.azurewebsites.net`
2. Navigate to: **Environment**
3. Check: Python version, PATH, environment variables

### 8. Error Pages

**From Azure Portal:**
1. Go to: `gait-analysis-api-simple` App Service
2. Navigate to: **Diagnose and solve problems**
3. Check: **Application Logs** or **Application Crashes**
4. Look for: Recent errors

## Most Critical Information

**Priority 1 (Most Important):**
- Application startup logs (last 50-100 lines)
- Any Python import errors
- Any "Module not found" errors
- Database connection errors

**Priority 2:**
- Build logs (Oryx build output)
- Deployment logs
- File system check (are files actually deployed?)

**Priority 3:**
- Process status
- Environment variables check

## Quick Diagnostic Commands

Run these and share the output:

```bash
# 1. Get recent application logs
az webapp log tail --name gait-analysis-api-simple --resource-group gait-analysis-rg-wus3 --output json | tail -50

# 2. Check deployment status
az webapp deployment list-publishing-profiles --name gait-analysis-api-simple --resource-group gait-analysis-rg-wus3

# 3. Check app settings
az webapp config appsettings list --name gait-analysis-api-simple --resource-group gait-analysis-rg-wus3

# 4. Check runtime configuration
az webapp config show --name gait-analysis-api-simple --resource-group gait-analysis-rg-wus3
```

## What to Look For

Common issues that cause 503 errors:

1. **Missing Dependencies**
   - Error: "ModuleNotFoundError: No module named 'X'"
   - Solution: Check requirements.txt installation

2. **Import Errors**
   - Error: "ImportError: cannot import name 'X'"
   - Solution: Check code structure

3. **Startup Script Issues**
   - Error: "startup.sh: not found" or "Permission denied"
   - Solution: Check file permissions and path

4. **Port Binding Issues**
   - Error: "Address already in use"
   - Solution: Check PORT environment variable

5. **Database Connection**
   - Error: "Connection refused" or "Authentication failed"
   - Solution: Check Cosmos DB credentials

6. **Memory Issues**
   - Error: "Out of memory" or "Killed"
   - Solution: Upgrade App Service plan

## How to Share Information

1. **Copy logs** from Azure Portal or CLI
2. **Screenshot** error messages (if visual)
3. **Share** the last 50-100 lines of relevant logs
4. **Include** timestamps if possible

This information will help identify the exact failure point and fix it.



