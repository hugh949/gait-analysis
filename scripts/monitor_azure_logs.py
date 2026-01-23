#!/usr/bin/env python3
"""
Azure Log Monitor - Fetches and analyzes recent logs from Azure App Service
Can be run periodically to check for errors and issues
"""
import subprocess
import json
import re
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# Azure App Service configuration
APP_NAME = "gaitanalysisapp"
RESOURCE_GROUP = "gait-analysis-rg-wus3"

def fetch_recent_logs(minutes: int = 5) -> List[str]:
    """Fetch recent logs from Azure App Service"""
    try:
        # Use az webapp log tail to get recent logs
        # Note: This streams logs, so we'll use a timeout
        cmd = [
            "az", "webapp", "log", "tail",
            "--name", APP_NAME,
            "--resource-group", RESOURCE_GROUP,
            "--timeout", str(minutes * 60)  # Convert minutes to seconds
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30  # Don't wait more than 30 seconds
        )
        
        if result.returncode == 0:
            return result.stdout.split('\n')
        else:
            print(f"Error fetching logs: {result.stderr}", file=sys.stderr)
            return []
    except subprocess.TimeoutExpired:
        print("Log fetch timed out", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return []

def analyze_logs_for_errors(logs: List[str]) -> Dict:
    """Analyze logs for errors and issues"""
    errors = []
    warnings = []
    critical_issues = []
    
    # Patterns to look for
    error_patterns = [
        r'ERROR',
        r'Exception',
        r'Traceback',
        r'Failed',
        r'❌',
        r'CRITICAL'
    ]
    
    warning_patterns = [
        r'WARNING',
        r'⚠️',
        r'Warning'
    ]
    
    # Critical patterns that need immediate attention
    critical_patterns = [
        r'Analysis not found',
        r'UnboundLocalError',
        r'IndentationError',
        r'SyntaxError',
        r'ModuleNotFoundError',
        r'ImportError',
        r'TimeoutError',
        r'ConnectionError'
    ]
    
    for line in logs:
        if not line.strip():
            continue
            
        # Check for critical issues
        for pattern in critical_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                critical_issues.append({
                    'line': line.strip(),
                    'pattern': pattern,
                    'timestamp': extract_timestamp(line)
                })
                break
        
        # Check for errors
        for pattern in error_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                # Skip if it's just a log level marker (ERROR level but not actual error)
                if 'HEARTBEAT' in line and 'UPDATE SUCCESS' in line:
                    continue
                if 'DIAGNOSTIC' in line:
                    continue
                errors.append({
                    'line': line.strip(),
                    'pattern': pattern,
                    'timestamp': extract_timestamp(line)
                })
                break
        
        # Check for warnings
        for pattern in warning_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                warnings.append({
                    'line': line.strip(),
                    'pattern': pattern,
                    'timestamp': extract_timestamp(line)
                })
                break
    
    return {
        'critical_issues': critical_issues,
        'errors': errors,
        'warnings': warnings,
        'total_lines': len(logs),
        'analysis_time': datetime.now().isoformat()
    }

def extract_timestamp(line: str) -> Optional[str]:
    """Extract timestamp from log line"""
    # Azure log format: 2026-01-23T19:05:11.1234567Z
    match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', line)
    if match:
        return match.group(1)
    return None

def check_processing_status(logs: List[str]) -> Dict:
    """Check current processing status from logs"""
    status = {
        'current_step': None,
        'progress': None,
        'frame_info': None,
        'analysis_id': None,
        'last_update': None
    }
    
    # Look for progress updates
    for line in reversed(logs):  # Start from most recent
        if 'PROGRESS:' in line or 'progress:' in line:
            # Extract step and progress
            step_match = re.search(r"step['\"]?\s*[:=]\s*['\"]?(\w+)", line, re.IGNORECASE)
            progress_match = re.search(r'progress[:\s]+(\d+)%', line, re.IGNORECASE)
            
            if step_match and not status['current_step']:
                status['current_step'] = step_match.group(1)
            if progress_match and not status['progress']:
                status['progress'] = int(progress_match.group(1))
        
        # Look for frame processing
        if 'Frame' in line and '/' in line:
            frame_match = re.search(r'Frame\s+(\d+)/(\d+)', line)
            if frame_match:
                status['frame_info'] = {
                    'current': int(frame_match.group(1)),
                    'total': int(frame_match.group(2))
                }
        
        # Look for analysis ID
        if 'Analysis ID:' in line:
            id_match = re.search(r'Analysis ID:\s*([a-f0-9-]+)', line, re.IGNORECASE)
            if id_match and not status['analysis_id']:
                status['analysis_id'] = id_match.group(1)
        
        if status['current_step'] and status['progress'] and status['frame_info']:
            break
    
    return status

def main():
    """Main monitoring function"""
    print("🔍 Fetching recent Azure logs...")
    logs = fetch_recent_logs(minutes=2)
    
    if not logs:
        print("❌ No logs retrieved")
        return 1
    
    print(f"✅ Retrieved {len(logs)} log lines")
    
    # Analyze for errors
    analysis = analyze_logs_for_errors(logs)
    
    # Check processing status
    status = check_processing_status(logs)
    
    # Print results
    print("\n" + "="*80)
    print("📊 LOG ANALYSIS RESULTS")
    print("="*80)
    
    print(f"\n🔍 Total log lines analyzed: {analysis['total_lines']}")
    print(f"⏰ Analysis time: {analysis['analysis_time']}")
    
    if status['current_step']:
        print(f"\n📈 Current Status:")
        print(f"   Step: {status['current_step']}")
        if status['progress']:
            print(f"   Progress: {status['progress']}%")
        if status['frame_info']:
            print(f"   Frames: {status['frame_info']['current']}/{status['frame_info']['total']}")
        if status['analysis_id']:
            print(f"   Analysis ID: {status['analysis_id']}")
    
    if analysis['critical_issues']:
        print(f"\n🚨 CRITICAL ISSUES FOUND: {len(analysis['critical_issues'])}")
        for issue in analysis['critical_issues'][:5]:  # Show first 5
            print(f"   [{issue['timestamp']}] {issue['line'][:100]}")
        return 2
    
    if analysis['errors']:
        print(f"\n❌ ERRORS FOUND: {len(analysis['errors'])}")
        # Filter out non-critical errors (like diagnostic logs)
        real_errors = [e for e in analysis['errors'] 
                      if 'HEARTBEAT' not in e['line'] 
                      and 'DIAGNOSTIC' not in e['line']
                      and 'UPDATE SUCCESS' not in e['line']]
        
        if real_errors:
            print(f"   (Filtered to {len(real_errors)} real errors)")
            for error in real_errors[:5]:  # Show first 5
                print(f"   [{error['timestamp']}] {error['line'][:100]}")
        else:
            print("   (All errors are diagnostic/heartbeat logs - not critical)")
    
    if analysis['warnings']:
        print(f"\n⚠️  WARNINGS: {len(analysis['warnings'])}")
        for warning in analysis['warnings'][:3]:  # Show first 3
            print(f"   [{warning['timestamp']}] {warning['line'][:100]}")
    
    if not analysis['critical_issues'] and not analysis['errors']:
        print("\n✅ No critical errors found - system appears to be running normally")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
