#!/bin/bash
# Proactive Validation Script
# Checks for common issues before deployment to prevent bugs

set -e

echo "🔍 Running Proactive Validation Checks..."
echo "=========================================="

ERRORS=0
WARNINGS=0

# Color codes
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

check_imports() {
    echo ""
    echo "📦 Checking Python imports..."
    
    # Check for common import errors
    if grep -r "from app.services.gait_analysis import get_gait_analysis_service" backend/ 2>/dev/null; then
        echo -e "${RED}❌ ERROR: Incorrect import - get_gait_analysis_service is in analysis_azure.py, not gait_analysis.py${NC}"
        ERRORS=$((ERRORS + 1))
    fi
    
    # Check for undefined imports
    python3 -c "
import sys
import ast
import os

def check_file(filepath):
    try:
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read(), filename=filepath)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module
                if module and module.startswith('app.'):
                    # Check if module exists
                    module_path = module.replace('.', '/')
                    if not os.path.exists(f'backend/{module_path}.py') and not os.path.exists(f'backend/{module_path}/__init__.py'):
                        print(f'⚠️  WARNING: Module {module} imported in {filepath} may not exist')
    except Exception as e:
        pass

for root, dirs, files in os.walk('backend/app'):
    for file in files:
        if file.endswith('.py'):
            check_file(os.path.join(root, file))
" || WARNINGS=$((WARNINGS + 1))
    
    echo -e "${GREEN}✓ Import checks complete${NC}"
}

check_service_initialization() {
    echo ""
    echo "🔧 Checking service initialization patterns..."
    
    # Check that services are initialized correctly
    if ! grep -q "def get_gait_analysis_service" backend/app/api/v1/analysis_azure.py; then
        echo -e "${RED}❌ ERROR: get_gait_analysis_service function not found${NC}"
        ERRORS=$((ERRORS + 1))
    fi
    
    # Check for proper error handling in service initialization
    if ! grep -q "try:" backend/app/api/v1/analysis_azure.py | head -1; then
        echo -e "${YELLOW}⚠️  WARNING: Service initialization may lack error handling${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
    
    echo -e "${GREEN}✓ Service initialization checks complete${NC}"
}

check_syntax() {
    echo ""
    echo "🔤 Checking Python syntax..."
    
    find backend/app -name "*.py" -type f | while read file; do
        if ! python3 -m py_compile "$file" 2>&1; then
            echo -e "${RED}❌ ERROR: Syntax error in $file${NC}"
            ERRORS=$((ERRORS + 1))
        fi
    done
    
    echo -e "${GREEN}✓ Syntax checks complete${NC}"
}

check_common_patterns() {
    echo ""
    echo "🔍 Checking for common bug patterns..."
    
    # Check for incorrect function calls
    if grep -r "get_gait_analysis_service()" backend/app/services/ 2>/dev/null | grep -v "#"; then
        echo -e "${YELLOW}⚠️  WARNING: get_gait_analysis_service() called from services/ - should be from api/${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
    
    # Check for hardcoded paths that might break
    if grep -r "/tmp/" backend/app/api/ 2>/dev/null | grep -v "tempfile"; then
        echo -e "${YELLOW}⚠️  WARNING: Hardcoded /tmp/ paths found - use tempfile module${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
    
    # Check for missing error handling in critical paths
    if grep -r "await db_service.create_analysis" backend/app/api/ | grep -v "try:"; then
        echo -e "${YELLOW}⚠️  WARNING: Database operations may lack error handling${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
    
    echo -e "${GREEN}✓ Pattern checks complete${NC}"
}

check_file_structure() {
    echo ""
    echo "📁 Checking file structure..."
    
    # Check that critical files exist
    CRITICAL_FILES=(
        "backend/app/api/v1/analysis_azure.py"
        "backend/app/services/gait_analysis.py"
        "backend/app/core/database_azure_sql.py"
        "backend/main_integrated.py"
    )
    
    for file in "${CRITICAL_FILES[@]}"; do
        if [ ! -f "$file" ]; then
            echo -e "${RED}❌ ERROR: Critical file missing: $file${NC}"
            ERRORS=$((ERRORS + 1))
        fi
    done
    
    echo -e "${GREEN}✓ File structure checks complete${NC}"
}

check_code_integrity() {
    echo ""
    echo "🛡️  Checking code integrity (Steps 1-2 protection)..."
    
    # Check for modifications to Step 1-2 that might break working code
    if git diff HEAD -- backend/app/services/gait_analysis.py | grep -E "(def _process_video_sync|def _lift_to_3d)" | grep -v "^\+.*#" | grep -v "^-.*#"; then
        echo -e "${YELLOW}⚠️  WARNING: Changes detected to Step 1-2 functions - verify they still work${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
    
    echo -e "${GREEN}✓ Code integrity checks complete${NC}"
}

# Run all checks
check_imports
check_service_initialization
check_syntax
check_common_patterns
check_file_structure
check_code_integrity

# Summary
echo ""
echo "=========================================="
echo "📊 Validation Summary:"
echo -e "   ${GREEN}Errors: $ERRORS${NC}"
echo -e "   ${YELLOW}Warnings: $WARNINGS${NC}"

if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}❌ Validation failed - fix errors before deploying${NC}"
    exit 1
elif [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Validation passed with warnings - review before deploying${NC}"
    exit 0
else
    echo -e "${GREEN}✅ All checks passed!${NC}"
    exit 0
fi
