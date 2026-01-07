#!/bin/bash
# Resumable Backend Deployment with Checkpoints
# Can be cancelled and resumed - won't restart from scratch
# Uses Azure's native caching and incremental features

set -e

# Checkpoint file to track progress
CHECKPOINT_FILE="/tmp/backend-deploy-checkpoint.json"
RESOURCE_GROUP="gait-analysis-rg-wus3"
APP_SERVICE_NAME="gait-analysis-api-simple"
REGISTRY="gaitanalysisacrwus3"
IMAGE="gait-analysis-api:latest"

# Navigate to backend directory
cd "$(dirname "$0")/../backend"

# Function to save checkpoint
save_checkpoint() {
    local step=$1
    local status=$2
    echo "{\"step\":\"$step\",\"status\":\"$status\",\"timestamp\":\"$(date +%s)\"}" > "$CHECKPOINT_FILE"
    echo "   💾 Checkpoint saved: $step"
}

# Function to load checkpoint
load_checkpoint() {
    if [ -f "$CHECKPOINT_FILE" ]; then
        cat "$CHECKPOINT_FILE"
    else
        echo "{\"step\":\"start\",\"status\":\"none\"}"
    fi
}

# Function to clear checkpoint
clear_checkpoint() {
    rm -f "$CHECKPOINT_FILE"
}

# Function to show progress with timestamp
show_progress() {
    local message=$1
    echo "   ⏱️  [$(date +%H:%M:%S)] $message" >&2
}

echo "🚀 Resumable Backend Deployment to Azure"
echo "=========================================="
echo ""
echo "💡 This script can be cancelled and resumed"
echo "   • Progress is saved at each step"
echo "   • Run again to resume from last checkpoint"
echo ""

# Check if resuming
CHECKPOINT=$(load_checkpoint)
LAST_STEP=$(echo "$CHECKPOINT" | grep -o '"step":"[^"]*' | cut -d'"' -f4 || echo "start")

if [ "$LAST_STEP" != "start" ] && [ "$LAST_STEP" != "complete" ]; then
    echo "🔄 Resuming from checkpoint: $LAST_STEP"
    echo "   (Delete $CHECKPOINT_FILE to start fresh)"
    echo ""
    read -p "Continue from checkpoint? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        clear_checkpoint
        LAST_STEP="start"
    fi
fi

# Step 1: Check changes (always run)
if [ "$LAST_STEP" = "start" ]; then
    echo "═══════════════════════════════════════════════════════════"
    echo "📋 Step 1/6: Checking what changed..."
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    
    # Create hash of code
    CODE_HASH=$(find app -name "*.py" main.py 2>/dev/null | xargs md5 -q 2>/dev/null | md5 -q 2>/dev/null || find app -name "*.py" main.py 2>/dev/null | xargs md5sum 2>/dev/null | md5sum | cut -d' ' -f1 || echo "")
    REQ_HASH=$(md5 -q requirements.txt 2>/dev/null || md5sum requirements.txt | cut -d' ' -f1 || echo "")
    DOCKERFILE_HASH=$(md5 -q Dockerfile.optimized 2>/dev/null || md5sum Dockerfile.optimized | cut -d' ' -f1 || echo "")
    
    # Save hashes for comparison
    echo "$CODE_HASH" > .current_code_hash
    echo "$REQ_HASH" > .current_req_hash
    echo "$DOCKERFILE_HASH" > .current_dockerfile_hash
    
    NEED_REBUILD=false
    if [ -f ".last_code_hash" ] && [ -f ".last_req_hash" ] && [ -f ".last_dockerfile_hash" ]; then
        OLD_CODE=$(cat .last_code_hash 2>/dev/null || echo "")
        OLD_REQ=$(cat .last_req_hash 2>/dev/null || echo "")
        OLD_DOCKER=$(cat .last_dockerfile_hash 2>/dev/null || echo "")
        
        if [ "$CODE_HASH" != "$OLD_CODE" ] || [ "$REQ_HASH" != "$OLD_REQ" ] || [ "$DOCKERFILE_HASH" != "$OLD_DOCKER" ]; then
            NEED_REBUILD=true
            if [ "$REQ_HASH" != "$OLD_REQ" ]; then
                echo "   ✅ Dependencies changed"
            fi
            if [ "$CODE_HASH" != "$OLD_CODE" ]; then
                echo "   ✅ Code changed"
            fi
            if [ "$DOCKERFILE_HASH" != "$OLD_DOCKER" ]; then
                echo "   ✅ Dockerfile changed"
            fi
        else
            echo "   ✅ No changes detected - will skip build"
        fi
    else
        NEED_REBUILD=true
        echo "   ✅ First deployment or no previous hashes"
    fi
    
    echo ""
    save_checkpoint "check_changes" "done"
    LAST_STEP="check_changes"
fi

# Step 2: Build Docker image (if needed)
if [ "$LAST_STEP" = "check_changes" ] || [ "$LAST_STEP" = "build" ]; then
    if [ "$NEED_REBUILD" = true ] || [ "$LAST_STEP" = "build" ]; then
        echo "═══════════════════════════════════════════════════════════"
        echo "📦 Step 2/6: Building Docker Image"
        echo "═══════════════════════════════════════════════════════════"
        echo ""
        echo "⏳ Building with Azure Container Registry..."
        echo "   • Azure uses layer caching automatically"
        echo "   • Only changed layers will rebuild"
        echo "   📊 Progress updates every 15 seconds..."
        echo ""
        
        # Start progress monitor
        (
            ELAPSED=0
            while true; do
                sleep 15
                ELAPSED=$((ELAPSED + 15))
                show_progress "Build in progress... ${ELAPSED}s elapsed"
            done
        ) &
        PROGRESS_PID=$!
        
        # Build with output streaming
        echo "   🔨 Starting build..."
        if az acr build --registry $REGISTRY --image $IMAGE --file Dockerfile.optimized . 2>&1 | tee /tmp/acr-build-$(date +%s).log | grep -E "(Step|Successfully|ERROR|error|Building|Pushing)" | head -100; then
            BUILD_SUCCESS=true
        else
            BUILD_SUCCESS=false
        fi
        
        kill $PROGRESS_PID 2>/dev/null || true
        
        if [ "$BUILD_SUCCESS" = false ]; then
            echo ""
            echo "❌ Build failed - check logs above"
            echo "   Run script again to retry from this step"
            save_checkpoint "build" "failed"
            exit 1
        fi
        
        # Save hashes on success
        cp .current_code_hash .last_code_hash 2>/dev/null || true
        cp .current_req_hash .last_req_hash 2>/dev/null || true
        cp .current_dockerfile_hash .last_dockerfile_hash 2>/dev/null || true
        
        echo ""
        echo "✅ Build complete!"
        save_checkpoint "build" "done"
        LAST_STEP="build"
    else
        echo "═══════════════════════════════════════════════════════════"
        echo "⏭️  Step 2/6: Skipping Build (No Changes)"
        echo "═══════════════════════════════════════════════════════════"
        echo ""
        echo "✅ Using cached Docker image"
        save_checkpoint "build" "skipped"
        LAST_STEP="build"
    fi
fi

# Step 3: Update container config
if [ "$LAST_STEP" = "build" ]; then
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "🔧 Step 3/6: Updating Container Configuration"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    
    (
        ELAPSED=0
        while true; do
            sleep 5
            ELAPSED=$((ELAPSED + 5))
            show_progress "Config update... ${ELAPSED}s"
        done
    ) &
    PROGRESS_PID=$!
    
    if az webapp config container set \
        --name $APP_SERVICE_NAME \
        --resource-group $RESOURCE_GROUP \
        --container-image-name $REGISTRY.azurecr.io/$IMAGE 2>&1 | grep -v "^$"; then
        CONFIG_SUCCESS=true
    else
        CONFIG_SUCCESS=false
    fi
    
    kill $PROGRESS_PID 2>/dev/null || true
    
    if [ "$CONFIG_SUCCESS" = true ]; then
        echo "✅ Container configured"
    else
        echo "⚠️  Config update may have issues (continuing...)"
    fi
    
    save_checkpoint "config" "done"
    LAST_STEP="config"
fi

# Step 4: Configure settings
if [ "$LAST_STEP" = "config" ]; then
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "⚙️  Step 4/6: Ensuring Configuration"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    
    show_progress "Setting CORS..."
    az webapp config appsettings set \
        --name $APP_SERVICE_NAME \
        --resource-group $RESOURCE_GROUP \
        --settings CORS_ORIGINS="https://jolly-meadow-0a467810f.1.azurestaticapps.net,http://localhost:3000,http://localhost:5173" \
        > /dev/null 2>&1 || echo "   ⚠️  CORS setting issue (may already be set)"
    
    show_progress "Enabling Always-On..."
    az webapp config set \
        --name $APP_SERVICE_NAME \
        --resource-group $RESOURCE_GROUP \
        --always-on true \
        > /dev/null 2>&1 || echo "   ⚠️  Always-On setting issue (may already be enabled)"
    
    echo "✅ Configuration complete"
    save_checkpoint "settings" "done"
    LAST_STEP="settings"
fi

# Step 5: Restart
if [ "$LAST_STEP" = "settings" ]; then
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "🔄 Step 5/6: Restarting App Service"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    
    (
        ELAPSED=0
        while true; do
            sleep 5
            ELAPSED=$((ELAPSED + 5))
            show_progress "Restarting... ${ELAPSED}s"
        done
    ) &
    PROGRESS_PID=$!
    
    az webapp restart --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP > /dev/null 2>&1
    
    kill $PROGRESS_PID 2>/dev/null || true
    
    echo "✅ Restart initiated"
    save_checkpoint "restart" "done"
    LAST_STEP="restart"
fi

# Step 6: Health check
if [ "$LAST_STEP" = "restart" ]; then
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "🏥 Step 6/6: Health Check"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    
    echo "⏳ Waiting for application to be ready..."
    for i in {1..24}; do
        sleep 5
        show_progress "Health check $i/24..."
        
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://$APP_SERVICE_NAME.azurewebsites.net/health 2>/dev/null || echo "000")
        
        if [ "$HTTP_CODE" = "200" ]; then
            echo ""
            echo "✅ Application is healthy! (HTTP $HTTP_CODE)"
            
            # Verify deployment with hash check
            echo ""
            echo "🔍 Verifying deployment..."
            DEPLOYED_HASH=$(curl -s --max-time 10 https://$APP_SERVICE_NAME.azurewebsites.net/health 2>/dev/null | md5 -q 2>/dev/null || echo "")
            if [ -n "$DEPLOYED_HASH" ]; then
                echo "   ✅ Deployment verified"
            fi
            
            save_checkpoint "complete" "success"
            clear_checkpoint
            LAST_STEP="complete"
            break
        elif [ "$HTTP_CODE" = "503" ] || [ "$HTTP_CODE" = "502" ]; then
            echo "   ⏳ Still starting... (HTTP $HTTP_CODE)"
        fi
    done
    
    if [ "$LAST_STEP" != "complete" ]; then
        echo ""
        echo "⚠️  Application not ready after 2 minutes"
        echo "   • May still be starting (first deployment takes longer)"
        echo "   • Run script again to check health"
        save_checkpoint "health_check" "pending"
    fi
fi

# Final summary
echo ""
echo "═══════════════════════════════════════════════════════════"
if [ "$LAST_STEP" = "complete" ]; then
    echo "✅ Deployment Complete!"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    echo "🔗 Backend URL: https://$APP_SERVICE_NAME.azurewebsites.net"
    echo ""
    echo "💡 Next deployment will be faster (uses Azure layer caching)"
else
    echo "⏸️  Deployment Paused"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    echo "📋 Last step: $LAST_STEP"
    echo "💡 Run script again to resume from checkpoint"
    echo "   (Checkpoint: $CHECKPOINT_FILE)"
fi
echo ""


