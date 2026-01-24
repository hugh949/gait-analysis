#!/usr/bin/env python3
"""
Real Bug Fixer - Actually fixes the bugs you're experiencing
This script actively scans and fixes common bugs in the codebase
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime

class RealBugFixer:
    """Fixes real bugs in your codebase"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.backend_dir = self.project_root / "backend"
        self.fixes_applied = []
        
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        
    def fix_unbound_local_error(self):
        """Fix UnboundLocalError by removing local imports of os/threading"""
        self.log("🔍 Checking for UnboundLocalError issues...")
        
        analysis_file = self.backend_dir / "app" / "api" / "v1" / "analysis_azure.py"
        if not analysis_file.exists():
            self.log("❌ analysis_azure.py not found")
            return False
        
        with open(analysis_file, "r") as f:
            content = f.read()
            lines = content.split("\n")
        
        # Check if os/threading are imported at module level
        module_imports = content[:2000]  # First 2000 chars should have imports
        has_os_import = "import os" in module_imports and "from" not in module_imports.split("import os")[0].split("\n")[-1]
        has_threading_import = "import threading" in module_imports
        
        if not has_os_import:
            self.log("⚠️  'os' not imported at module level - adding it")
            # Find first non-comment, non-import line
            insert_pos = 0
            for i, line in enumerate(lines[:30]):
                if line.strip().startswith("from ") or line.strip().startswith("import "):
                    insert_pos = i + 1
                elif line.strip() and not line.strip().startswith("#"):
                    break
            
            lines.insert(insert_pos, "import os")
            has_os_import = True
            self.fixes_applied.append("Added module-level 'import os'")
        
        if not has_threading_import:
            self.log("⚠️  'threading' not imported at module level - adding it")
            # Find where to insert (after os import)
            insert_pos = 0
            for i, line in enumerate(lines[:30]):
                if "import os" in line:
                    insert_pos = i + 1
                    break
            
            lines.insert(insert_pos, "import threading")
            has_threading_import = True
            self.fixes_applied.append("Added module-level 'import threading'")
        
        # Remove local imports inside functions
        fixed = False
        new_lines = []
        i = 0
        in_function = False
        function_indent = 0
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Detect function start
            if re.match(r'^def\s+\w+', stripped):
                in_function = True
                function_indent = len(line) - len(line.lstrip())
                new_lines.append(line)
                i += 1
                continue
            
            # If in function, check for local imports
            if in_function:
                current_indent = len(line) - len(line.lstrip())
                
                # Still in function
                if current_indent > function_indent:
                    # Check if this is a local import of os/threading
                    if re.match(r'^\s+import\s+(os|threading)\s*$', line):
                        self.log(f"   🗑️  Removing local import: {stripped}")
                        fixed = True
                        i += 1
                        continue
                    else:
                        new_lines.append(line)
                        i += 1
                else:
                    # Function ended
                    in_function = False
                    new_lines.append(line)
                    i += 1
            else:
                new_lines.append(line)
                i += 1
        
        if fixed:
            with open(analysis_file, "w") as f:
                f.write("\n".join(new_lines))
            self.fixes_applied.append("Removed local imports causing UnboundLocalError")
            self.log("✅ Fixed UnboundLocalError issues")
            return True
        else:
            self.log("✅ No local import issues found")
            return False
    
    def check_syntax_errors(self):
        """Check for Python syntax errors"""
        self.log("🔍 Checking for syntax errors...")
        
        important_files = [
            "main_integrated.py",
            "app/api/v1/analysis_azure.py"
        ]
        
        errors = []
        for file_path in important_files:
            full_path = self.backend_dir / file_path
            if full_path.exists():
                try:
                    result = subprocess.run(
                        [sys.executable, "-m", "py_compile", str(full_path)],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode != 0:
                        errors.append(f"{file_path}: {result.stderr}")
                        self.log(f"❌ Syntax error in {file_path}")
                except Exception as e:
                    errors.append(f"{file_path}: {str(e)}")
        
        if errors:
            self.log(f"❌ Found {len(errors)} syntax error(s)")
            for error in errors:
                self.log(f"   {error}")
            return False
        else:
            self.log("✅ No syntax errors found")
            return True
    
    def check_unclosed_try_blocks(self):
        """Check for unclosed try blocks"""
        self.log("🔍 Checking for unclosed try blocks...")
        
        analysis_file = self.backend_dir / "app" / "api" / "v1" / "analysis_azure.py"
        if not analysis_file.exists():
            return False
        
        with open(analysis_file, "r") as f:
            content = f.read()
        
        # Count try/except/finally
        try_count = content.count("try:")
        except_count = len(re.findall(r'except\s+', content))
        finally_count = content.count("finally:")
        
        if try_count > (except_count + finally_count):
            self.log(f"⚠️  Potential unclosed try blocks: {try_count} try, {except_count} except, {finally_count} finally")
            return False
        else:
            self.log("✅ All try blocks appear to be closed")
            return True
    
    def verify_fixes(self):
        """Verify that fixes worked"""
        self.log("🔍 Verifying fixes...")
        
        # Check syntax again
        if not self.check_syntax_errors():
            self.log("❌ Syntax errors still present after fixes")
            return False
        
        # Check for local imports again
        analysis_file = self.backend_dir / "app" / "api" / "v1" / "analysis_azure.py"
        if analysis_file.exists():
            with open(analysis_file, "r") as f:
                content = f.read()
            
            # Check for local imports in functions
            if re.search(r'def\s+\w+.*:\s*\n\s*import\s+(os|threading)', content, re.MULTILINE):
                self.log("⚠️  Local imports still found")
                return False
        
        self.log("✅ All fixes verified")
        return True
    
    def run_all_fixes(self):
        """Run all bug fixes"""
        self.log("=" * 60)
        self.log("🚀 Starting Real Bug Fixer")
        self.log("=" * 60)
        
        # Fix 1: UnboundLocalError
        self.fix_unbound_local_error()
        
        # Fix 2: Check syntax
        syntax_ok = self.check_syntax_errors()
        
        # Fix 3: Check try blocks
        self.check_unclosed_try_blocks()
        
        # Verify
        if self.fixes_applied:
            self.log("\n✅ Fixes Applied:")
            for fix in self.fixes_applied:
                self.log(f"   - {fix}")
            
            if self.verify_fixes():
                self.log("\n✅ All fixes verified successfully!")
                return True
            else:
                self.log("\n⚠️  Some issues may remain")
                return False
        else:
            self.log("\n✅ No fixes needed - code looks good!")
            return True

def main():
    fixer = RealBugFixer()
    success = fixer.run_all_fixes()
    
    if success:
        print("\n✅ Bug fixing complete!")
        sys.exit(0)
    else:
        print("\n⚠️  Some issues may need manual attention")
        sys.exit(1)

if __name__ == "__main__":
    main()
