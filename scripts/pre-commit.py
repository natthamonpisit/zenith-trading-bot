#!/usr/bin/env python3
"""
Pre-commit hook to prevent committing secrets
Install: ln -s ../../scripts/pre-commit.py .git/hooks/pre-commit
"""
import re
import sys
import subprocess

# Patterns to detect
SECRET_PATTERNS = [
    (r'AIza[0-9A-Za-z_-]{35}', 'Google API Key'),
    (r'sk-[a-zA-Z0-9]{48}', 'OpenAI API Key'),
    (r'xox[baprs]-[0-9a-zA-Z]{10,48}', 'Slack Token'),
    (r'ghp_[a-zA-Z0-9]{36}', 'GitHub Personal Access Token'),
    (r'AWS[0-9A-Z]{16,}', 'AWS Key'),
    (r'(password|passwd|pwd)\s*=\s*["\'][^"\']+["\']', 'Password in code'),
]

def check_for_secrets():
    """Check staged files for secrets"""
    
    # Get list of staged files
    result = subprocess.run(
        ['git', 'diff', '--cached', '--name-only'],
        capture_output=True,
        text=True
    )
    
    staged_files = result.stdout.strip().split('\n')
    
    found_secrets = False
    
    for file_path in staged_files:
        if not file_path:
            continue
            
        # Skip binary files and node_modules
        if any(x in file_path for x in ['.pyc', 'node_modules', '.git', 'venv']):
            continue
        
        try:
            # Get staged content
            result = subprocess.run(
                ['git', 'show', f':{file_path}'],
                capture_output=True,
                text=True
            )
            content = result.stdout
            
            # Check each pattern
            for pattern, name in SECRET_PATTERNS:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    print(f"❌ BLOCKED: Found {name} in {file_path}")
                    print(f"   Matched: {matches[0][:20]}...")
                    found_secrets = True
                    
        except Exception as e:
            continue
    
    if found_secrets:
        print("\n🚨 COMMIT BLOCKED: Secrets detected!")
        print("💡 Remove secrets and use environment variables instead.")
        print("   Check .env (which should be in .gitignore)")
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(check_for_secrets())
