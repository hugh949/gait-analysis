# Development Standards

## Core Principles

1. **Syntax and Indentation First**: All code must pass syntax validation before any commit
2. **Systematic Problem Solving**: Track and learn from build issues to prevent recurrence
3. **Mature Engineering Practices**: Act as a project manager, architect, and engineer
4. **Forward Progress**: Make systematic improvements, not circular fixes

## Pre-Commit Requirements

### Mandatory Checks

Before **every** commit, the following must pass:

1. **Python Syntax Validation**
   ```bash
   ./scripts/validate-python-syntax.sh
   ```
   - All Python files must compile without errors
   - No syntax errors
   - No indentation errors

2. **Critical File Verification**
   - `backend/main_integrated.py` - Must compile
   - `backend/app/api/v1/analysis_azure.py` - Must compile
   - `backend/app/services/gait_analysis.py` - Must compile
   - All other Python files in `backend/app/` - Must compile

3. **Import Verification**
   - All imports must be present at module level
   - No circular imports
   - No usage of unimported modules

### Common Issues to Prevent

#### Indentation Errors
- **Try/Except Blocks**: Always indent code inside try/except
- **Function Calls**: Multi-line arguments must be indented
- **Nested Blocks**: Maintain consistent 4-space indentation
- **Dictionary/List Literals**: In function calls, indent properly

#### Syntax Errors
- **Docstrings**: Must have opening and closing triple quotes
- **Function Definitions**: Proper indentation for function body
- **Async Functions**: Correct async/await syntax
- **Type Hints**: Proper syntax for type annotations

#### Import Errors
- **Module-Level Imports**: All imports at top of file
- **Missing Imports**: Verify all used modules are imported
- **Import Order**: Standard library → Third-party → Local imports

## Validation Process

### Before Every Edit
1. Read the file to understand context
2. Identify the specific change needed
3. Plan the edit carefully

### During Edit
1. Maintain existing indentation style
2. Follow Python PEP 8 guidelines
3. Keep function signatures consistent
4. Preserve existing error handling patterns

### After Edit
1. **MANDATORY**: Run `python3 -m py_compile <file>` on edited file
2. **MANDATORY**: Run `./scripts/validate-python-syntax.sh` for all files
3. Check that imports are still valid
4. Verify no new syntax errors introduced

### Before Commit
1. Run full validation: `./scripts/pre-commit-checks.sh`
2. Review changes in context
3. Ensure no regressions introduced
4. Document any significant changes

## Build Issue Tracking

### Process
1. When a build issue is reported, document it in `BUILD_ISSUES_LOG.md`
2. Identify root cause (not just symptoms)
3. Fix systematically
4. Add prevention measures
5. Update validation scripts if needed

### Learning from Issues
- Don't just fix the immediate problem
- Understand why it happened
- Add checks to prevent recurrence
- Update documentation

## Code Quality Standards

### Python Code
- **Indentation**: 4 spaces (no tabs)
- **Line Length**: Maximum 120 characters (prefer 100)
- **Imports**: Grouped (stdlib, third-party, local)
- **Docstrings**: All functions and classes
- **Type Hints**: Use where appropriate
- **Error Handling**: Comprehensive and informative

### File Organization
- **Imports**: Top of file, grouped
- **Constants**: After imports
- **Classes**: Before functions
- **Functions**: Logical grouping
- **Module-Level Code**: Minimal, only initialization

### Error Messages
- **Descriptive**: Explain what went wrong
- **Actionable**: Suggest how to fix
- **Contextual**: Include relevant information
- **Structured**: Use consistent format

## Architecture Principles

### Separation of Concerns
- **API Layer**: Request/response handling
- **Service Layer**: Business logic
- **Data Layer**: Persistence and retrieval
- **Core Layer**: Shared utilities and models

### Error Handling
- **Custom Exceptions**: Use domain-specific exceptions
- **Error Propagation**: Don't swallow errors silently
- **Logging**: Comprehensive logging at appropriate levels
- **User Feedback**: Clear error messages to users

### Testing Strategy
- **Syntax Validation**: Always (automated)
- **Import Validation**: Always (automated)
- **Functional Testing**: As needed
- **Integration Testing**: For critical paths

## Commit Standards

### Commit Messages
- **Clear**: Describe what was changed
- **Specific**: Include file names if relevant
- **Context**: Explain why if not obvious
- **Format**: 
  ```
  Brief summary (50 chars max)
  
  Detailed explanation if needed:
  - What was changed
  - Why it was changed
  - Any related issues
  ```

### Commit Size
- **Focused**: One logical change per commit
- **Complete**: Don't commit broken code
- **Validated**: All checks must pass

## Continuous Improvement

### Review Process
1. After each build issue, review what went wrong
2. Update validation scripts if needed
3. Improve documentation
4. Share learnings in BUILD_ISSUES_LOG.md

### Process Refinement
- Regularly review and improve validation scripts
- Update standards based on new issues
- Refine checklists based on experience
- Automate more checks where possible

## Responsibility

As the development assistant, I commit to:

1. **Always validate syntax before committing**
2. **Learn from every build issue**
3. **Prevent recurring problems**
4. **Maintain high code quality standards**
5. **Make systematic forward progress**
6. **Act with maturity and professionalism**

This is a complex application with critical functionality. We will not compromise on basic coding practices.
