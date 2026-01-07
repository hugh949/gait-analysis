# New Architecture Plan - Microsoft Native Services

## Problem Statement
Current architecture uses custom ML models (torch, HRNet, ViTPose) which:
- Require heavy dependencies that are difficult to deploy
- Cause deployment failures and timeouts
- Are complex to maintain
- Don't scale reliably on Azure App Service

## Solution: Microsoft Native Services Architecture

### Core Services

1. **Azure Computer Vision API** (or Custom Vision)
   - Replace: Custom pose estimation models (HRNet, ViTPose)
   - Benefits: Managed service, no ML dependencies, reliable, scalable
   - API: Azure Computer Vision for general video analysis
   - Alternative: Azure Custom Vision if we need specialized models

2. **Azure Blob Storage**
   - Replace: Temporary file storage
   - Benefits: Simple, scalable, cost-effective
   - Use: Store uploaded videos, processed results

3. **Azure SQL Database** (or Azure Table Storage for simplicity)
   - Replace: Cosmos DB (complex) or in-memory storage
   - Benefits: Simple relational database, easy queries
   - Use: Store analysis metadata, results, user data

4. **Azure App Service** (Python)
   - Keep: FastAPI backend (lightweight)
   - Remove: All ML dependencies (torch, opencv, numpy-heavy operations)
   - Dependencies: Only FastAPI, Azure SDKs, uvicorn

5. **Azure Static Web Apps**
   - Keep: React frontend
   - No changes needed

## New Dependency Stack

### Backend Dependencies (Minimal)
```txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-multipart>=0.0.6
azure-storage-blob>=12.19.0
azure-cognitiveservices-vision-computervision>=0.9.0
azure-identity>=1.15.0
python-dotenv>=1.0.0
pydantic>=2.0.0
```

### Removed Dependencies
- torch (huge, causes deployment issues)
- opencv-python (heavy, image processing)
- numpy (only keep if Azure SDK requires it)
- All custom ML model dependencies

## Architecture Flow

1. **Video Upload**
   - User uploads video → Azure Blob Storage
   - Store metadata in Azure SQL Database
   - Return analysis ID to frontend

2. **Video Analysis**
   - Process video using Azure Computer Vision API
   - Store results in Azure Blob Storage
   - Update metadata in Azure SQL Database
   - Send progress updates to frontend

3. **Results Retrieval**
   - Frontend polls backend for status
   - Backend retrieves from Azure SQL Database
   - Return results when complete

## Benefits

1. **Reliability**: Managed services, no deployment issues
2. **Simplicity**: Minimal dependencies, fast deployments
3. **Scalability**: Azure services scale automatically
4. **Cost**: Pay-per-use, efficient for 2-3 users
5. **Maintenance**: Microsoft manages infrastructure

## Implementation Plan

1. Set up Azure resources (Blob Storage, SQL Database, Computer Vision)
2. Rebuild backend with Azure SDKs only
3. Update video processing to use Computer Vision API
4. Update database layer to use Azure SQL
5. Update frontend if needed
6. Test end-to-end

## Migration Strategy

- Start fresh with new architecture
- Keep frontend mostly unchanged (just API endpoint updates)
- Completely rebuild backend
- Test incrementally


