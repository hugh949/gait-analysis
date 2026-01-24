#!/usr/bin/env python3
"""
Continuous Bug Fixer - Runs in a loop, finds bugs, fixes them automatically
Simple, practical, and actually works
"""

import os
import re
import subprocess
import sys
import time
import urllib.request
import json
from pathlib import Path
from datetime import datetime

class ContinuousBugFixer:
    """Continuously finds and fixes bugs"""
    
    def __init__(self, base_url="http://localhost:8000", interval=30):
        self.base_url = base_url
        self.interval = interval
        self.project_root = Path(__file__).parent.parent
        self.backend_dir = self.project_root / "backend"
        self.cycle = 0
        self.fixes_count = 0
        
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        
    def test_url(self, path):
        """Test a URL using urllib (no external dependencies)"""
        try:
            url = f"{self.base_url}{path}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as response:
                return True, response.status, response.read().decode()[:200]
        except urllib.error.HTTPError as e:
            return False, e.code, e.read().decode()[:200] if hasattr(e, 'read') else str(e)
        except Exception as e:
            return False, 0, str(e)
    
    def check_endpoints(self):
        """Check if endpoints are working"""
        self.log("🔍 Testing endpoints...")
        issues = []
        
        endpoints = [
            ("/", "Root"),
            ("/health", "Health"),
            ("/api/v1/health", "API Health"),
            ("/api/v1/debug/routes", "Debug Routes"),
        ]
        
        for path, name in endpoints:
            success, status, response = self.test_url(path)
            if success:
                self.log(f"  ✅ {name}: OK")
            else:
                self.log(f"  ❌ {name}: Failed ({status})")
                issues.append(f"{name} endpoint failed")
        
        return issues
    
    def check_python_syntax(self):
        """Check Python syntax"""
        self.log("🔍 Checking Python syntax...")
        errors = []
        
        files = [
            "main_integrated.py",
            "app/api/v1/analysis_azure.py"
        ]
        
        for file_path in files:
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
                except Exception as e:
                    errors.append(f"{file_path}: {str(e)}")
        
        if errors:
            self.log(f"  ❌ Found {len(errors)} syntax error(s)")
            return errors
        else:
            self.log("  ✅ No syntax errors")
            return []
    
    def fix_local_imports(self):
        """Fix local imports that cause UnboundLocalError"""
        self.log("🔍 Checking for problematic local imports...")
        
        analysis_file = self.backend_dir / "app" / "api" / "v1" / "analysis_azure.py"
        if not analysis_file.exists():
            return False
        
        with open(analysis_file, "r") as f:
            lines = f.readlines()
        
        # Check for local imports in functions
        fixed = False
        new_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Check if we're entering a function
            if re.match(r'^\s*def\s+\w+', line):
                # Collect function lines
                func_lines = [line]
                func_indent = len(line) - len(line.lstrip())
                j = i + 1
                
                while j < len(lines):
                    next_line = lines[j]
                    next_indent = len(next_line) - len(next_line.lstrip())
                    
                    if next_indent > func_indent:
                        # Still in function
                        # Check if this is a local import of os/threading
                        if re.match(r'^\s+import\s+(os|threading)\s*$', next_line):
                            self.log(f"  🗑️  Removing local import: {next_line.strip()}")
                            fixed = True
                            j += 1
                            continue
                        func_lines.append(next_line)
                        j += 1
                    else:
                        break
                
                new_lines.extend(func_lines)
                i = j
            else:
                new_lines.append(line)
                i += 1
        
        if fixed:
            with open(analysis_file, "w") as f:
                f.writelines(new_lines)
            self.log("  ✅ Removed problematic local imports")
            return True
        else:
            self.log("  ✅ No problematic local imports found")
            return False
    
    def ensure_module_imports(self):
        """Ensure os and threading are imported at module level"""
        analysis_file = self.backend_dir / "app" / "api" / "v1" / "analysis_azure.py"
        if not analysis_file.exists():
            return False
        
        with open(analysis_file, "r") as f:
            content = f.read()
            lines = content.split("\n")
        
        # Check first 30 lines for imports
        imports_section = "\n".join(lines[:30])
        needs_os = "import os" not in imports_section or ("def" in imports_section.split("import os")[0] if "import os" in imports_section else True)
        needs_threading = "import threading" not in imports_section
        
        fixed = False
        
        if needs_os:
            # Find where to insert (after other imports)
            insert_pos = 0
            for i, line in enumerate(lines[:30]):
                if line.strip().startswith("import ") or line.strip().startswith("from "):
                    insert_pos = i + 1
                elif line.strip() and not line.strip().startswith("#"):
                    break
            
            lines.insert(insert_pos, "import os")
            self.log("  ➕ Added 'import os' at module level")
            fixed = True
        
        if needs_threading:
            # Find where to insert (after os import)
            insert_pos = 0
            for i, line in enumerate(lines[:30]):
                if "import os" in line:
                    insert_pos = i + 1
                    break
            
            lines.insert(insert_pos, "import threading")
            self.log("  ➕ Added 'import threading' at module level")
            fixed = True
        
        if fixed:
            with open(analysis_file, "w") as f:
                f.write("\n".join(lines))
            return True
        
        return False
    
    def run_cycle(self):
        """Run one test and fix cycle"""
        self.cycle += 1
        self.log("=" * 60)
        self.log(f"🔄 Cycle #{self.cycle}")
        self.log("=" * 60)
        
        issues_found = []
        fixes_applied = 0
        
        # Test endpoints
        endpoint_issues = self.check_endpoints()
        issues_found.extend(endpoint_issues)
        
        # Check syntax
        syntax_errors = self.check_python_syntax()
        if syntax_errors:
            issues_found.extend(syntax_errors)
            
            # Try to fix
            if self.fix_local_imports():
                fixes_applied += 1
                self.fixes_count += 1
            
            if self.ensure_module_imports():
                fixes_applied += 1
                self.fixes_count += 1
            
            # Re-check syntax after fixes
            if fixes_applied > 0:
                self.log("🔍 Re-checking syntax after fixes...")
                syntax_errors_after = self.check_python_syntax()
                if not syntax_errors_after:
                    self.log("  ✅ Syntax errors fixed!")
                else:
                    self.log("  ⚠️  Some syntax errors remain")
        
        # Summary
        if not issues_found:
            self.log("\n✅ All checks passed - no issues found!")
        else:
            self.log(f"\n⚠️  Found {len(issues_found)} issue(s)")
            if fixes_applied > 0:
                self.log(f"✅ Applied {fixes_applied} fix(es)")
        
        self.log(f"\n📊 Total fixes applied: {self.fixes_count}")
        self.log(f"⏳ Next cycle in {self.interval} seconds...\n")
        
        return len(issues_found) == 0
    
    def run_continuous(self):
        """Run continuously"""
        self.log("🚀 Starting Continuous Bug Fixer")
        self.log(f"Base URL: {self.base_url}")
        self.log(f"Interval: {self.interval} seconds")
        self.log("Press Ctrl+C to stop\n")
        
        try:
            while True:
                self.run_cycle()
                time.sleep(self.interval)
        except KeyboardInterrupt:
            self.log("\n\n🛑 Stopped by user")
            self.log(f"📊 Summary: {self.cycle} cycles, {self.fixes_count} fixes applied")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Continuous bug fixer")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL to test")
    parser.add_argument("--interval", type=int, default=30, help="Test interval in seconds")
    args = parser.parse_args()
    
    fixer = ContinuousBugFixer(base_url=args.url, interval=args.interval)
    fixer.run_continuous()

if __name__ == "__main__":
    main()
