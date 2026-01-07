# GitHub Actions Troubleshooting Guide

## Common Errors and Solutions

### Error: "Process completed with exit code 1"

This means one of the workflow steps failed. Check the workflow logs to see which step failed.

**How to check:**
1. Go to: https://github.com/hugh949/Gait-Analysis/actions
2. Click on the failed workflow run
3. Expand each step to see which one failed
4. Look for error messages in red

### Common Failure Points

#### 1. Azure Login Failed
**Error:** `Login failed with Error: Using auth-type: SERVICE_PRINCIPAL. Not all values are present.`

**Solution:**
- Verify `AZURE_CREDENTIALS` secret is set correctly
- The JSON must include all 4 fields: `clientId`, `clientSecret`, `subscriptionId`, `tenantId`
- Run `./scripts/create-azure-service-principal.sh` to regenerate credentials
- Make sure the secret name is exactly `AZURE_CREDENTIALS` (case-sensitive)

#### 2. Frontend Build Failed
**Error:** `npm ci failed` or `npm run build failed`

**Solution:**
- Check if `frontend/package.json` exists
- Verify Node.js version (should be 18)
- Check for syntax errors in frontend code
- Try running `npm install` locally to see if there are dependency issues

#### 3. Azure Resources Not Found
**Error:** `Resource group not found` or `App Service not found`

**Solution:**
- Verify resources exist: `az group show --name gait-analysis-rg-wus3`
- Check resource names match the workflow:
  - Resource Group: `gait-analysis-rg-wus3`
  - App Service: `gaitanalysisapp`
  - ACR: `gaitacr737`

#### 4. Docker Build Failed
**Error:** `az acr build failed` or `Dockerfile.integrated not found`

**Solution:**
- Verify `backend/Dockerfile.integrated` exists
- Check that `backend/frontend-dist` directory exists (frontend must be built first)
- Verify `backend/main_integrated.py` exists
- Check Dockerfile syntax

#### 5. Health Check Failed
**Error:** `Application health check failed`

**Solution:**
- This may be normal - the container might need more time to start
- Check Azure Portal logs: App Service → Log stream
- Verify `WEBSITES_PORT=8000` is set in App Service settings
- Check container logs for application errors

### Debugging Steps

1. **Check Workflow Logs:**
   - Go to Actions tab
   - Click on the failed workflow
   - Expand each step to see detailed logs

2. **Check Azure Portal:**
   - App Service → Log stream (for application logs)
   - App Service → Container settings (for container status)
   - App Service → Configuration (for environment variables)

3. **Verify Secrets:**
   - Go to: https://github.com/hugh949/Gait-Analysis/settings/secrets/actions
   - Verify `AZURE_CREDENTIALS` is set
   - Verify format is correct JSON

4. **Test Locally:**
   - Try building frontend: `cd frontend && npm ci && npm run build`
   - Try building Docker image locally
   - Test the application locally

### Getting More Information

**View detailed workflow logs:**
```bash
# The logs are in GitHub Actions UI, but you can also check:
# Go to: https://github.com/hugh949/Gait-Analysis/actions
# Click on workflow run → Click on job → Expand steps
```

**Check Azure resources:**
```bash
az group show --name gait-analysis-rg-wus3
az webapp show --name gaitanalysisapp --resource-group gait-analysis-rg-wus3
az acr show --name gaitacr737
```

**View App Service logs:**
```bash
az webapp log tail --name gaitanalysisapp --resource-group gait-analysis-rg-wus3
```

**Check container status:**
```bash
az webapp show --name gaitanalysisapp --resource-group gait-analysis-rg-wus3 --query "{state:state, defaultHostName:defaultHostName}"
```

### Still Having Issues?

1. Check the specific error message in the workflow logs
2. Verify all secrets are set correctly
3. Verify Azure resources exist and are accessible
4. Check Azure Portal for any service issues
5. Review the workflow file for any configuration issues

