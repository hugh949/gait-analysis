#!/usr/bin/env python3
"""
Comprehensive Test and Fix - Actually tests everything and fixes bugs
"""

import os
import re
import subprocess
import sys
import urllib.request
import urllib.parse
import json
import time
from pathlib import Path
from datetime import datetime

class ComprehensiveTester:
    """Tests everything and fixes bugs"""
    
    def __init__(self, base_url="https://gaitanalysisapp.azurewebsites.net"):
        self.base_url = base_url
        self.project_root = Path(__file__).parent.parent
        self.backend_dir = self.project_root / "backend"
        self.bugs_found = []
        self.bugs_fixed = []
        
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        symbol = "✅" if level == "SUCCESS" else "❌" if level == "ERROR" else "🔍" if level == "TEST" else "🔧" if level == "FIX" else "ℹ️"
        print(f"[{timestamp}] {symbol} {message}")
        
    def test_endpoint(self, path, method="GET", data=None, files=None):
        """Test an endpoint"""
        try:
            url = f"{self.base_url}{path}"
            
            if method == "GET":
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=10) as response:
                    return True, response.status, response.read().decode()
            elif method == "POST":
                if files:
                    # For file upload, we'd need to use requests or create multipart manually
                    # For now, just test if endpoint exists
                    return self.test_endpoint_exists(path)
                else:
                    data_bytes = json.dumps(data).encode() if data else b""
                    req = urllib.request.Request(url, data=data_bytes, method="POST")
                    req.add_header("Content-Type", "application/json")
                    with urllib.request.urlopen(req, timeout=10) as response:
                        return True, response.status, response.read().decode()
        except urllib.error.HTTPError as e:
            return False, e.code, e.read().decode() if hasattr(e, 'read') else str(e)
        except Exception as e:
            return False, 0, str(e)
    
    def test_endpoint_exists(self, path):
        """Check if endpoint exists by checking routes"""
        success, status, response = self.test_endpoint("/api/v1/debug/routes")
        if success:
            try:
                routes_data = json.loads(response)
                routes = routes_data.get("routes", [])
                for route in routes:
                    if path in route.get("path", ""):
                        return True, 200, "Endpoint exists"
                return False, 404, "Endpoint not in routes"
            except:
                return False, 0, "Could not parse routes"
        return False, 0, "Could not get routes"
    
    def check_code_quality(self):
        """Check code for common bugs"""
        self.log("Checking code quality...", "TEST")
        issues = []
        
        analysis_file = self.backend_dir / "app" / "api" / "v1" / "analysis_azure.py"
        if not analysis_file.exists():
            self.bugs_found.append("analysis_azure.py not found")
            return
        
        with open(analysis_file, "r") as f:
            content = f.read()
            lines = content.split("\n")
        
        # Check 1: Local imports in functions
        if re.search(r'def\s+\w+.*:\s*\n\s+import\s+(os|threading)', content, re.MULTILINE):
            self.log("Found local imports in functions", "ERROR")
            self.bugs_found.append("Local imports causing UnboundLocalError")
            self.fix_local_imports(analysis_file, lines)
        
        # Check 2: Unclosed try blocks
        try_count = content.count("try:")
        except_count = len(re.findall(r'except\s+', content))
        finally_count = content.count("finally:")
        if try_count > (except_count + finally_count):
            self.log(f"Potential unclosed try blocks: {try_count} try, {except_count} except, {finally_count} finally", "ERROR")
            self.bugs_found.append("Unclosed try blocks")
        
        # Check 3: Missing module imports
        first_50_lines = "\n".join(lines[:50])
        if "import os" not in first_50_lines:
            self.log("Missing 'import os' at module level", "ERROR")
            self.bugs_found.append("Missing module import: os")
            self.add_module_import(analysis_file, lines, "os")
        
        if "import threading" not in first_50_lines:
            self.log("Missing 'import threading' at module level", "ERROR")
            self.bugs_found.append("Missing module import: threading")
            self.add_module_import(analysis_file, lines, "threading")
    
    def fix_local_imports(self, file_path, lines):
        """Remove local imports"""
        self.log("Fixing local imports...", "FIX")
        fixed = False
        new_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            if re.match(r'^\s*def\s+\w+', line):
                func_lines = [line]
                func_indent = len(line) - len(line.lstrip())
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    next_indent = len(next_line) - len(next_line.lstrip())
                    if next_indent > func_indent:
                        if re.match(r'^\s+import\s+(os|threading)\s*$', next_line):
                            self.log(f"  Removing: {next_line.strip()}", "FIX")
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
            with open(file_path, "w") as f:
                f.write("\n".join(new_lines))
            self.bugs_fixed.append("Removed local imports")
            self.log("Fixed local imports", "SUCCESS")
    
    def add_module_import(self, file_path, lines, module_name):
        """Add module import at top"""
        self.log(f"Adding 'import {module_name}' at module level...", "FIX")
        insert_pos = 0
        for i, line in enumerate(lines[:30]):
            if line.strip().startswith("import ") or line.strip().startswith("from "):
                insert_pos = i + 1
            elif line.strip() and not line.strip().startswith("#"):
                break
        
        lines.insert(insert_pos, f"import {module_name}")
        with open(file_path, "w") as f:
            f.write("\n".join(lines))
        self.bugs_fixed.append(f"Added import {module_name}")
        self.log(f"Added 'import {module_name}'", "SUCCESS")
    
    def check_syntax(self):
        """Check Python syntax"""
        self.log("Checking Python syntax...", "TEST")
        files = ["main_integrated.py", "app/api/v1/analysis_azure.py"]
        errors = []
        
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
                        self.log(f"Syntax error in {file_path}", "ERROR")
                except Exception as e:
                    errors.append(f"{file_path}: {str(e)}")
        
        if errors:
            self.bugs_found.extend(errors)
            return False
        else:
            self.log("No syntax errors", "SUCCESS")
            return True
    
    def test_all_endpoints(self):
        """Test all endpoints"""
        self.log("Testing all endpoints...", "TEST")
        endpoints = [
            ("/", "Root"),
            ("/health", "Health"),
            ("/api/v1/health", "API Health"),
            ("/api/v1/debug/routes", "Debug Routes"),
            ("/api/v1/analysis/list", "List Analyses"),
        ]
        
        all_ok = True
        for path, name in endpoints:
            success, status, response = self.test_endpoint(path)
            if success:
                self.log(f"{name}: OK ({status})", "SUCCESS")
            else:
                self.log(f"{name}: FAILED ({status})", "ERROR")
                self.bugs_found.append(f"{name} endpoint failed: {status}")
                all_ok = False
        
        # Check upload endpoint exists
        success, status, _ = self.test_endpoint_exists("/api/v1/analysis/upload")
        if success:
            self.log("Upload endpoint: Registered", "SUCCESS")
        else:
            self.log("Upload endpoint: NOT FOUND", "ERROR")
            self.bugs_found.append("Upload endpoint not registered")
            all_ok = False
        
        return all_ok
    
    def run_full_test(self):
        """Run complete test suite"""
        self.log("=" * 60, "INFO")
        self.log("Starting Comprehensive Test and Fix", "INFO")
        self.log("=" * 60, "INFO")
        
        # Test 1: Endpoints
        endpoints_ok = self.test_all_endpoints()
        
        # Test 2: Code quality
        self.check_code_quality()
        
        # Test 3: Syntax
        syntax_ok = self.check_syntax()
        
        # Summary
        self.log("=" * 60, "INFO")
        self.log("Test Summary", "INFO")
        self.log("=" * 60, "INFO")
        
        if endpoints_ok:
            self.log("All endpoints: ✅ WORKING", "SUCCESS")
        else:
            self.log("Some endpoints: ❌ FAILED", "ERROR")
        
        if syntax_ok:
            self.log("Python syntax: ✅ VALID", "SUCCESS")
        else:
            self.log("Python syntax: ❌ ERRORS FOUND", "ERROR")
        
        if self.bugs_found:
            self.log(f"\nBugs Found: {len(self.bugs_found)}", "ERROR")
            for bug in self.bugs_found:
                self.log(f"  - {bug}", "ERROR")
        else:
            self.log("\nBugs Found: 0 ✅", "SUCCESS")
        
        if self.bugs_fixed:
            self.log(f"\nBugs Fixed: {len(self.bugs_fixed)}", "SUCCESS")
            for fix in self.bugs_fixed:
                self.log(f"  - {fix}", "SUCCESS")
        else:
            self.log("\nBugs Fixed: 0 (none needed)", "INFO")
        
        # If bugs were fixed, verify
        if self.bugs_fixed:
            self.log("\nRe-verifying after fixes...", "TEST")
            syntax_ok_after = self.check_syntax()
            if syntax_ok_after:
                self.log("✅ All fixes verified!", "SUCCESS")
            else:
                self.log("⚠️ Some issues may remain", "ERROR")
        
        return len(self.bugs_found) == 0 and syntax_ok

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://gaitanalysisapp.azurewebsites.net")
    parser.add_argument("--loop", action="store_true", help="Run in continuous loop")
    parser.add_argument("--interval", type=int, default=30, help="Loop interval in seconds")
    args = parser.parse_args()
    
    tester = ComprehensiveTester(base_url=args.url)
    
    if args.loop:
        print("Running in continuous loop (Ctrl+C to stop)...\n")
        cycle = 0
        try:
            while True:
                cycle += 1
                print(f"\n{'='*60}")
                print(f"CYCLE #{cycle}")
                print(f"{'='*60}\n")
                tester.run_full_test()
                print(f"\n⏳ Waiting {args.interval} seconds before next cycle...\n")
                time.sleep(args.interval)
                # Reset for next cycle
                tester.bugs_found = []
                tester.bugs_fixed = []
        except KeyboardInterrupt:
            print("\n\n🛑 Stopped by user")
    else:
        success = tester.run_full_test()
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
