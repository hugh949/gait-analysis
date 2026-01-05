# Faster Docker Builds on Azure

## Why Builds Are Slow

### Current Build Time: 5-10+ minutes

**Main Bottlenecks:**
1. **Large ML Dependencies** (~3-4GB downloads):
   - PyTorch + torchvision: ~2GB
   - mmpose + mmcv: ~500MB
   - OpenCV + dependencies: ~200MB
   - Other ML libraries: ~500MB

2. **Compilation Time**:
   - Some packages compile from source
   - No build caching between runs

3. **ACR Build Agent**:
   - Default agent is shared and may be slower
   - No dedicated build resources

## Azure Settings to Speed Up Builds

### 1. Enable ACR Build Caching ✅ (Recommended)

**Current Status:** Check if enabled
```bash
az acr show --name gaitanalysisacreus2 --query "buildProperties" -o json
```

**Enable caching:**
```bash
# ACR automatically caches layers, but ensure it's enabled
az acr update --name gaitanalysisacreus2 --admin-enabled true
```

**Benefits:** 
- Reuses layers that haven't changed
- Can reduce build time by 50-70% on subsequent builds

### 2. Use Multi-Stage Builds ✅ (Implemented)

**File:** `Dockerfile.optimized`

**Benefits:**
- Separates build dependencies from runtime
- Smaller final image
- Better layer caching
- Faster builds when only code changes

**Usage:**
```bash
az acr build --registry gaitanalysisacreus2 \
  --image gait-analysis-api:latest \
  --file Dockerfile.optimized .
```

### 3. Upgrade ACR SKU (If Needed)

**Current:** Check current SKU
```bash
az acr show --name gaitanalysisacreus2 --query "sku.name" -o tsv
```

**Options:**
- **Basic**: Shared CPU, slower builds
- **Standard**: Better performance, faster builds
- **Premium**: Best performance, fastest builds

**Upgrade:**
```bash
az acr update --name gaitanalysisacreus2 --sku Standard
# or
az acr update --name gaitanalysisacreus2 --sku Premium
```

### 4. Use ACR Tasks with Better Agents

**Create optimized build task:**
```bash
az acr task create \
  --registry gaitanalysisacreus2 \
  --name build-backend \
  --context . \
  --file backend/Dockerfile.optimized \
  --image gait-analysis-api:{{.Run.ID}} \
  --image gait-analysis-api:latest \
  --commit-trigger-enabled false \
  --base-image-trigger-enabled false
```

### 5. Pre-build Base Image with Dependencies

**Strategy:** Create a base image with all ML dependencies pre-installed

**Benefits:**
- Dependencies only install once
- Application code changes = fast rebuilds
- Can reduce build time to 1-2 minutes

**Implementation:**
1. Create `Dockerfile.base` with just dependencies
2. Build and push base image
3. Use base image in main Dockerfile

### 6. Use Azure Container Instances for Builds

**Alternative:** Build locally or on ACI for faster builds

**Not recommended** for ACR integration, but faster for local testing.

## Quick Wins (Immediate)

### ✅ Use Optimized Dockerfile

```bash
# Use the optimized Dockerfile
cd backend
az acr build --registry gaitanalysisacreus2 \
  --image gait-analysis-api:latest \
  --file Dockerfile.optimized .
```

### ✅ Enable Build Caching

ACR automatically caches, but ensure:
- Requirements.txt changes trigger rebuilds
- Code changes don't rebuild dependencies

### ✅ Monitor Build Progress

```bash
# Watch build in real-time
az acr build --registry gaitanalysisacreus2 \
  --image gait-analysis-api:latest . \
  --no-logs false
```

## Expected Improvements

| Method | Current Time | Optimized Time | Improvement |
|--------|-------------|----------------|-------------|
| First Build | 8-10 min | 8-10 min | No change |
| Code Change | 8-10 min | 1-2 min | 80% faster |
| Deps Change | 8-10 min | 8-10 min | No change |
| With Premium SKU | 8-10 min | 5-7 min | 30% faster |

## Recommendations

1. **Immediate:** Use `Dockerfile.optimized` for better caching
2. **Short-term:** Upgrade to Standard SKU if on Basic
3. **Long-term:** Create base image with pre-installed dependencies

## Cost vs Speed Trade-off

- **Basic SKU**: $5/month, slower builds
- **Standard SKU**: $20/month, faster builds
- **Premium SKU**: $50/month, fastest builds

For development, Standard SKU is usually the best balance.

