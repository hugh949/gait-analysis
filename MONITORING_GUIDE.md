# Azure Log Monitoring Guide

## Overview
This guide explains how to monitor Azure logs automatically without manually pasting logs.

## Methods

### Method 1: API Endpoints (Recommended)

Once deployed, you can access logs via API endpoints:

#### 1. Get Recent Logs
```bash
curl https://gaitanalysisapp.azurewebsites.net/api/v1/logs/recent?lines=100
```

#### 2. Analyze Logs for Errors
```bash
curl https://gaitanalysisapp.azurewebsites.net/api/v1/logs/analyze?analysis_id=YOUR_ANALYSIS_ID
```

#### 3. Health Check
```bash
curl https://gaitanalysisapp.azurewebsites.net/api/v1/logs/health-check
```

### Method 2: Monitoring Script

Use the Python monitoring script:

```bash
cd /Users/hughrashid/Cursor/Gait-Analysis
python scripts/monitor_azure_logs.py
```

This script will:
- Fetch recent logs from Azure
- Analyze for errors, warnings, and critical issues
- Check processing status
- Report any stuck analyses

### Method 3: Azure CLI (Direct)

If you have Azure CLI configured:

```bash
# Stream logs in real-time
az webapp log tail --name gaitanalysisapp --resource-group gait-analysis-rg-wus3

# Download logs
az webapp log download --name gaitanalysisapp --resource-group gait-analysis-rg-wus3 --log-file logs.zip
```

## Automatic Error Detection

The system now automatically detects:

1. **Stuck Analyses**: Analyses processing for >10 minutes without updates
2. **Critical Errors**: Exceptions, Tracebacks, ImportErrors, etc.
3. **Real Errors**: Filters out diagnostic/heartbeat logs
4. **Processing Status**: Current step, progress, frame count

## Integration with AI Assistant

You can now ask me to:
- "Check recent logs for errors"
- "Analyze logs for analysis ID X"
- "Check if any analyses are stuck"
- "What's the current processing status?"

I can use the API endpoints or monitoring script to fetch and analyze logs automatically.

## Example Usage

```bash
# Check for errors in last 5 minutes
curl "https://gaitanalysisapp.azurewebsites.net/api/v1/logs/analyze?minutes=5"

# Get recent error logs only
curl "https://gaitanalysisapp.azurewebsites.net/api/v1/logs/recent?lines=200&filter_level=ERROR"

# Search for specific text
curl "https://gaitanalysisapp.azurewebsites.net/api/v1/logs/recent?search=Analysis%20not%20found"
```

## Next Steps

1. Deploy the new endpoints
2. Use the API to monitor logs automatically
3. Set up periodic monitoring if needed
4. No more manual log pasting required!
