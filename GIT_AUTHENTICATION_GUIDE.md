# Git Authentication Guide

## Why You Weren't Prompted

If you weren't prompted for credentials when running `git push`, it's likely because:

1. **Git is using cached credentials** (stored in macOS keychain)
2. **Git is using SSH** (instead of HTTPS)
3. **There are no new commits to push** (already up to date)

## Check Your Current Setup

### Check Remote URL
```bash
git remote get-url origin
```

**If it shows `git@github.com:`** → Using SSH (no token needed, uses SSH keys)
**If it shows `https://github.com/`** → Using HTTPS (needs token or stored credentials)

### Check Stored Credentials
```bash
git config --get credential.helper
```

**If it shows `osxkeychain`** → Credentials are stored in macOS keychain
**If empty** → No credential helper configured

### Check if Already Up to Date
```bash
git status -sb
```

**If it shows `ahead N`** → You have commits to push
**If it shows `up to date`** → Nothing to push

## Solutions

### Option 1: Force Authentication Prompt (Clear Cached Credentials)

If credentials are cached and you want to use your Personal Access Token:

```bash
# Remove cached credentials
git credential-osxkeychain erase <<EOF
host=github.com
protocol=https
EOF

# Or remove all GitHub credentials from keychain
# Go to: Applications → Utilities → Keychain Access
# Search for "github.com"
# Delete the entry

# Then try push again
git push -u origin main
```

### Option 2: Use Personal Access Token Directly in URL

You can include the token in the remote URL (less secure, but works):

```bash
# Get your Personal Access Token
# Then update remote URL
git remote set-url origin https://YOUR_TOKEN@github.com/hugh949/gait-analysis.git

# Or with username and token
git remote set-url origin https://hugh949:YOUR_TOKEN@github.com/hugh949/gait-analysis.git

# Then push
git push -u origin main
```

**Note**: Your token will be stored in `.git/config` (visible in plain text)

### Option 3: Use SSH Instead (Recommended for Long-term)

If you prefer SSH keys (no token needed after setup):

```bash
# Check if you have SSH key
ls -la ~/.ssh/id_*.pub

# If you don't have one, generate it
ssh-keygen -t ed25519 -C "your_email@example.com"

# Copy public key
cat ~/.ssh/id_ed25519.pub

# Add to GitHub: https://github.com/settings/keys
# Click "New SSH key"
# Paste your public key

# Change remote to SSH
git remote set-url origin git@github.com:hugh949/gait-analysis.git

# Test connection
ssh -T git@github.com

# Push (no authentication needed)
git push -u origin main
```

### Option 4: Verify Push is Needed

If nothing happened, check if you have commits to push:

```bash
# Check status
git status -sb

# Check what commits are ahead
git log --oneline origin/main..HEAD

# If nothing to push, make a test commit
echo "# Test" >> README.md
git add README.md
git commit -m "Test commit"
git push -u origin main
```

## Recommended Approach

For automatic deployments with GitHub Actions:

1. **Use HTTPS** with Personal Access Token (simpler)
2. **Clear cached credentials** if they're old/incorrect
3. **Enter token when prompted** during `git push`

### Step-by-Step

```bash
# 1. Check remote URL (should be HTTPS)
git remote get-url origin

# 2. If using SSH, switch to HTTPS
git remote set-url origin https://github.com/hugh949/gait-analysis.git

# 3. Clear any cached credentials
git credential-osxkeychain erase <<EOF
host=github.com
protocol=https
EOF

# 4. Try push (should prompt for credentials)
git push -u origin main
```

**When prompted**:
- Username: `hugh949`
- Password: (paste your GitHub Personal Access Token)

## Troubleshooting

### Still Not Prompted?

1. **Check if using SSH**:
   ```bash
   git remote get-url origin
   # If shows git@github.com, switch to HTTPS
   ```

2. **Check credential helper**:
   ```bash
   git config --global credential.helper
   # If shows osxkeychain, credentials are cached
   ```

3. **Manually clear keychain**:
   - Open: Applications → Utilities → Keychain Access
   - Search for: "github.com"
   - Delete entries
   - Try push again

4. **Use token in URL** (temporary):
   ```bash
   git remote set-url origin https://hugh949:YOUR_TOKEN@github.com/hugh949/gait-analysis.git
   git push -u origin main
   ```

## Summary

- **If using SSH**: No token needed (uses SSH keys)
- **If using HTTPS**: Token needed (may be cached)
- **If nothing to push**: Make a commit first
- **If cached**: Clear credentials or use token in URL



