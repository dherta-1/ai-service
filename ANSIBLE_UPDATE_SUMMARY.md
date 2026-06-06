# Ansible Deployment Update - Image-Based Deployment

## What Changed

The Ansible deployment playbook has been updated to **pull pre-built images from GHCR instead of cloning the repository**.

### Changes Made

#### 1. **Removed Git Operations** (`deploy.yml`)
- ❌ Removed git repository cloning
- ❌ Removed git pull/update tasks
- ❌ Removed `git` from system packages

**Why?** Images contain all code and dependencies. No need to clone source code.

#### 2. **Updated Image Registry Configuration**
- Changed from generic `your-registry.com` to **GHCR (GitHub Container Registry)**
- Added documentation for GitHub PAT setup
- Supports both public and private images

#### 3. **Simplified Deployment Flow**
```
Old Flow:
  Docker → User → Directories → Clone Repo → Generate Configs → Pull Images → Setup → Start

New Flow:
  Docker → User → Directories → Generate Configs → Pull Images → Setup → Start
```

## Updated Files

| File | Change |
|------|--------|
| `deploy.yml` | Removed git clone/update tasks |
| `group_vars/production.yml` | Updated to GHCR, removed project_repo vars |
| `group_vars/production.yml.template` | Updated to GHCR, removed project_repo vars |
| `ansible/DEPLOYMENT_SUMMARY.md` | **NEW** - Updated deployment guide |

## Configuration Steps

### Before Deployment

1. **Copy templates:**
   ```bash
   cd ansible
   cp inventory/production.ini.template inventory/production.ini
   cp group_vars/production.yml.template group_vars/production.yml
   ```

2. **Edit `inventory/production.ini`:**
   ```ini
   [production]
   your-server.com ansible_host=123.45.67.89 ansible_user=ubuntu
   ```

3. **Edit `group_vars/production.yml`:**
   ```yaml
   # Your GHCR registry
   docker_registry: "ghcr.io/your-org"
   docker_username: "your-github-username"  # Only if private images
   docker_password: "ghp_xxxx..."           # GitHub PAT with read:packages
   
   # Your domain and settings
   domain: yourdomain.com
   postgres_password: "change-me!"
   minio_root_password: "change-me!"
   llm_api_key: "your-api-key"
   jwt_secret_key: "random-string"
   ```

## Deployment Command

Same as before:

```bash
ansible-playbook deploy.yml
```

Or with specific tags:

```bash
# Just configure and restart
ansible-playbook deploy.yml --tags config,deploy

# Pull new images and restart
ansible-playbook deploy.yml --tags images,deploy

# Full deployment
ansible-playbook deploy.yml
```

## GitHub Container Registry (GHCR)

### For Public Images (No Auth)
```yaml
docker_registry: "ghcr.io/your-org"
docker_username: ""
docker_password: ""
```

### For Private Images (Need Auth)

1. **Create GitHub Personal Access Token:**
   - Go to https://github.com/settings/tokens/new
   - Scopes: `read:packages`
   - Copy token

2. **Configure:**
   ```yaml
   docker_registry: "ghcr.io/your-org"
   docker_username: "your-github-username"
   docker_password: "ghp_xxxxxxxxxxxx"  # Your PAT
   ```

### Publishing Images to GHCR

From your CI/CD pipeline or local machine:

```bash
# Build your images
docker build -t ghcr.io/your-org/dherta-backend:latest .

# Login to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u your-username --password-stdin

# Push
docker push ghcr.io/your-org/dherta-backend:latest
```

## Deployment Timeline

```
┌─ First Deployment (30-45 min) ────────────────────────┐
│                                                        │
│  • Docker setup: 5 min                                 │
│  • Image pull: 3-5 min                                │
│  • Model download: 15-30 min (one-time)              │
│  • Service startup: 2-3 min                           │
│  • Verification: <1 min                               │
│                                                        │
└────────────────────────────────────────────────────────┘

┌─ Subsequent Deployments (5-10 min) ──────────────────┐
│                                                       │
│  • Image pull: 2-3 min (cached if not updated)      │
│  • Service restart: 1-2 min                          │
│                                                       │
└───────────────────────────────────────────────────────┘
```

## Server Directory Structure

After deployment, on your server:

```
/home/deploy/dherta-ai-service/
└── docker/
    ├── docker-compose.yml          (generated)
    ├── Caddyfile                   (generated)
    ├── .env                        (generated, mode 0600)
    ├── init.sql
    └── volumes/
        ├── postgres data
        ├── redis data
        ├── kafka data
        ├── minio data
        ├── models (paddle, browsers)
        └── caddy config
```

## Key Advantages

✅ **Simpler Deployment** — No git operations, just pull images
✅ **Faster Iterations** — Update images without cloning repo
✅ **Cleaner Separation** — Code in images, config in templates
✅ **CI/CD Friendly** — Images built separately, deployed via Ansible
✅ **Security** — Images can be signed and scanned before deployment
✅ **Consistency** — Same image deployed everywhere, no source variations

## Migration from Old Setup

If you had a previous deployment with git cloning:

```bash
# Clear old directory (optional)
ssh ubuntu@your-server.com
rm -rf /home/deploy/dherta-ai-service/

# Run new deployment
ansible-playbook deploy.yml
```

Or keep the old setup and it will still work (Ansible is idempotent).

## Troubleshooting

### Image Not Found
```bash
# Check image exists
docker pull ghcr.io/your-org/dherta-backend:latest

# Verify registry URL in group_vars
grep docker_registry group_vars/production.yml
```

### Authentication Failed
```bash
# Test GHCR login locally
echo $GITHUB_TOKEN | docker login ghcr.io -u your-username --password-stdin

# Update credentials in group_vars/production.yml
```

### Setup Profile Hangs
```bash
# Check logs on server
ssh ubuntu@your-server.com
cd /home/deploy/dherta-ai-service/docker
docker compose logs setup
```

## Documentation Files

| File | Purpose |
|------|---------|
| **ANSIBLE_UPDATE_SUMMARY.md** | This file - what changed |
| **DEPLOYMENT_SUMMARY.md** | Updated deployment guide |
| **QUICK_START.md** | 5-minute setup guide |
| **README.md** | Complete reference |
| **DEPLOYMENT.md** | Detailed workflow |

## Next Steps

1. **Update your image build process** to push to GHCR
2. **Configure group_vars/production.yml** with your GHCR path
3. **Test deployment** with `ansible-playbook deploy.yml --check`
4. **Deploy** with `ansible-playbook deploy.yml`

---

**Note:** The playbook still supports any Docker registry (Docker Hub, private registries, etc.) via the `docker_registry` variable. GHCR is just the default recommendation.
