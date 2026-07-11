# Container Authentication Guide

This guide explains how to authenticate Claude Code CLI inside Docker containers.

## Quick Start

### Option 1: Use Host Credentials (Automatic)

The easiest method - your host credentials are automatically mounted and copied into the container:

```bash
# Launch interactive container
./scripts/launch_container_shell.sh

# Credentials are automatically set up!
# Check status:
ls -la ~/.claude/.credentials.json

# Run experiments immediately:
python scripts/manage_experiment.py run \
    --tiers-dir tests/fixtures/tests/test-001 \
    --tiers T0 --runs 1 -v
```

### Option 2: Authenticate Inside Container (Manual)

If host credentials aren't available or need refresh:

```bash
# Launch interactive container
./scripts/launch_container_shell.sh

# Inside container, authenticate:
claude auth

# Follow the prompts to complete OAuth flow
# Then run experiments:
python scripts/manage_experiment.py run \
    --tiers-dir tests/fixtures/tests/test-001 \
    --tiers T0 --runs 1 -v
```

### Option 3: Use API Key (Environment Variable)

For automated workflows or CI/CD:

```bash
# Set API key on host
export ANTHROPIC_API_KEY=your-key-here

# Launch container (key is passed through)
./scripts/launch_container_shell.sh

# Or run single experiment:
./scripts/run_experiment_in_container.sh \
    --tiers-dir tests/fixtures/tests/test-001 \
    --tiers T0 --runs 1 -v
```

## How It Works

### Automatic Credential Mounting

When you launch a container with our scripts:

1. **Host credentials detected** at `~/.claude/.credentials.json`
2. **Copied to temp directory** with proper permissions (644)
3. **Mounted into container** at `/tmp/host-creds/.credentials.json`
4. **Entrypoint copies** to `/home/scylla/.claude/.credentials.json` (600)
5. **Claude CLI uses** the credentials automatically

### Container Startup Flow

```
Host Script → Docker Container
    ↓
Entrypoint: ensure_clean_claude_environment()
    ↓
Check: /tmp/host-creds/.credentials.json
    ├─ Found → Copy to ~/.claude/.credentials.json ✓
    └─ Not Found → Warn user to run 'claude auth'
```

### Welcome Message

When launching an interactive shell, you'll see:

```
==========================================
Scylla Container Shell
==========================================
Working Directory: /workspace
Python Version: Python 3.14.2

Credentials: /home/scylla/.claude/.credentials.json
  ✓ Credentials found

Run experiments:
  python scripts/manage_experiment.py run \
    --tiers-dir tests/fixtures/tests/test-001 \
    --tiers T0 --runs 1 -v

Authenticate Claude (if needed):
  claude auth

==========================================
```

## Troubleshooting

### Issue: "No Claude Code credentials found"

**Symptom:**

```
[WARN] No Claude Code credentials or ANTHROPIC_API_KEY found
[WARN] Run 'claude auth' inside container to authenticate
```

**Solutions:**

1. **Check host credentials exist:**

   ```bash
   ls -la ~/.claude/.credentials.json
   ```

2. **Authenticate on host first:**

   ```bash
   claude auth
   # Then launch container again
   ./scripts/launch_container_shell.sh
   ```

3. **Authenticate inside container:**

   ```bash
   ./scripts/launch_container_shell.sh
   # Inside container:
   claude auth
   ```

4. **Use API key instead:**

   ```bash
   export ANTHROPIC_API_KEY=your-key-here
   ./scripts/launch_container_shell.sh
   ```

### Issue: "Authentication expired"

**Symptom:**

```
Error: Your authentication token has expired
```

**Solution:**

Refresh authentication inside container:

```bash
# Inside container:
claude auth
```

The credentials file is writable (600 permissions) so Claude can refresh tokens.

### Issue: "Permission denied on .credentials.json"

**Symptom:**

```
Permission denied: /home/scylla/.claude/.credentials.json
```

**Solution:**

This should not happen with our scripts. If it does:

1. **Check container user:**

   ```bash
   # Inside container:
   whoami  # Should be 'scylla'
   ls -la ~/.claude/.credentials.json  # Should be owned by scylla
   ```

2. **Rebuild image:**

   ```bash
   docker build -t scylla-runner:latest -f docker/Dockerfile .
   ```

### Issue: "claude: command not found"

**Symptom:**

```
bash: claude: command not found
```

**Solution:**

The Claude CLI should be installed in the image. Check:

```bash
# Inside container:
which claude
# Should output: /usr/local/bin/claude

# If not found, rebuild image:
docker build -t scylla-runner:latest -f docker/Dockerfile .
```

### Issue: Cannot authenticate interactively (OAuth flow fails)

**Symptom:**

```
Error: Cannot open browser for authentication
```

**Solution:**

Use API key instead:

```bash
# On host, export key:
export ANTHROPIC_API_KEY=your-key-here

# Launch container:
./scripts/launch_container_shell.sh

# Inside container, verify:
echo $ANTHROPIC_API_KEY
```

## Advanced: Persistent Credentials

### Save credentials back to host

If you authenticated inside the container and want to save credentials to host:

```bash
# Inside container:
cat ~/.claude/.credentials.json

# On host (in another terminal):
docker cp <container-name>:/home/scylla/.claude/.credentials.json ~/.claude/.credentials.json
chmod 600 ~/.claude/.credentials.json
```

### Named container with persistent credentials

For long-running containers where you want credentials to persist:

```bash
# Launch with custom name (modify script to remove --rm flag)
./scripts/launch_container_shell.sh my-persistent-session

# Authenticate inside:
claude auth

# Exit container
exit

# Re-attach later - credentials are still there:
docker start my-persistent-session
docker exec -it my-persistent-session bash

# Credentials preserved!
ls -la ~/.claude/.credentials.json
```

## Security Notes

### Credential Permissions

- **Host credentials**: 600 (owner read/write only)
- **Temp mount directory**: 644 (world-readable, needed for container access)
- **Container credentials**: 600 (owner read/write only)
- **Container .claude directory**: 700 (owner only)

### Credential Cleanup

When using `run_experiment_in_container.sh`:

- Temp credentials cleaned up automatically via trap on EXIT
- Located at `${PROJECT_DIR}/.tmp-container-creds/`

When using `launch_container_shell.sh`:

- Container removed on exit (--rm flag)
- Temp credentials cleaned up via trap on EXIT

### API Keys

If passing `ANTHROPIC_API_KEY` as environment variable:

- Only visible inside container
- Not stored anywhere
- Removed when container exits

## Testing Authentication

### Quick test

```bash
# Launch container
./scripts/launch_container_shell.sh

# Inside container:
# 1. Check credentials exist
ls -la ~/.claude/.credentials.json

# 2. Test Claude CLI
claude --version

# 3. Test API call (simple prompt)
claude "Say hello"

# 4. If successful, run experiment
python scripts/manage_experiment.py run \
    --tiers-dir tests/fixtures/tests/test-001 \
    --tiers T0 --runs 1 --max-subtests 1 -v
```

### Verify credential mounting

```bash
# Inside container:
echo "Checking credential sources:"
echo ""
echo "Mounted credentials:"
ls -la /tmp/host-creds/.credentials.json 2>/dev/null || echo "  Not found"
echo ""
echo "Container credentials:"
ls -la ~/.claude/.credentials.json 2>/dev/null || echo "  Not found"
echo ""
echo "API Key set:"
[ -n "$ANTHROPIC_API_KEY" ] && echo "  Yes" || echo "  No"
```

## See Also

- [Container Usage Guide](./container-usage.md) - General container usage
- [Container Architecture](./container-architecture.md) - Technical details
- [Claude Code CLI Docs](https://code.claude.com/docs) - Official Claude documentation
