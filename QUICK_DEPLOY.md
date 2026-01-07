# Quick Deployment Guide

## ⚡ Fastest Method: Smart Incremental Deployment

**For code-only changes (most common):**
```bash
./scripts/deploy-backend-smart.sh
```
- **Time: 30-60 seconds** ⚡
- **Method: ZIP deployment (no Docker)**
- **When: Python code changed, dependencies unchanged**

**For dependency changes:**
```bash
./scripts/deploy-backend-smart.sh
```
- **Time: 3-8 minutes** 🐳
- **Method: Docker build (necessary)**
- **When: requirements.txt changed**

**For no changes:**
```bash
./scripts/deploy-backend-smart.sh
```
- **Time: 30 seconds** ⏭️
- **Method: Skip deployment**
- **When: Nothing changed**

## 📊 Speed Comparison

| Scenario | Old Script | Smart Script | Speedup |
|----------|-----------|--------------|---------|
| Code only | 9+ minutes | 30-60 seconds | **10-20x faster** |
| Dependencies | 9+ minutes | 3-8 minutes | Same |
| No changes | 9+ minutes | 30 seconds | **18x faster** |

## 🎯 How It Works

1. **Detects what changed** (code vs dependencies)
2. **Chooses fastest method** automatically
3. **Shows progress** every 3-10 seconds
4. **Saves time** by skipping unnecessary steps

## ✅ Always Use Smart Script

The smart script (`deploy-backend-smart.sh`) is **10-20x faster** for code-only changes because it:
- Uses ZIP deployment instead of Docker
- Skips dependency installation if unchanged
- Shows frequent progress updates
- Automatically switches App Service mode

## 🚀 Frontend Deployment

```bash
./scripts/deploy-frontend-incremental.sh
```
- Fast for frontend code changes
- Only rebuilds changed files


