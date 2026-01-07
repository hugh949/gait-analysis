# Critical Deployment Requirement: Frequent Progress Messages

## User Requirement
**ALWAYS provide frequent progress messages during ALL builds and deployments.**

This is a critical requirement for the user's workflow. The user needs to know:
- That the system is NOT hung
- That processing is continuing
- How long operations have been running
- When to wait vs. when something is wrong

## Implementation Guidelines

### For ALL Deployment Scripts:
1. **Long-running operations (>30 seconds)** MUST show progress updates every 10-15 seconds
2. **Medium operations (10-30 seconds)** should show updates every 5-10 seconds
3. **Short operations (<10 seconds)** should show start/complete messages

### Progress Message Format:
```
   ⏱️  [Operation] in progress... [X] seconds elapsed (still [doing what]...)
```

### Example Implementation:
```bash
# Start progress indicator in background
(
  ELAPSED=0
  while true; do
    sleep 10
    ELAPSED=$((ELAPSED + 10))
    echo "   ⏱️  Build in progress... ${ELAPSED} seconds elapsed (still building...)"
  done
) &
PROGRESS_PID=$!

# Run the actual command
COMMAND_OUTPUT=$(long-running-command 2>&1)
EXIT_CODE=$?

# Kill progress indicator
kill $PROGRESS_PID 2>/dev/null || true
wait $PROGRESS_PID 2>/dev/null || true
```

### Operations That Need Progress Updates:
- Docker builds (5-10 minutes)
- File uploads (30 seconds - 2 minutes)
- Azure CLI commands that may hang
- npm builds (1-2 minutes)
- Application restarts (30-60 seconds)
- Health check polling (60+ seconds)

### Remember:
- **This requirement applies to ALL deployments, regardless of project or situation**
- **The user has emphasized this multiple times - it's critical for their workflow**
- **Never deploy without progress messages for long-running operations**


