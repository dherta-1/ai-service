# Ansible Deployment Overview

## What Was Created

A complete Ansible automation setup for deploying the Dherta AI Service to production. This enables **one-command deployment** of the entire stack to a clean Ubuntu server.

## Directory Structure

```
ansible/
├── ansible.cfg                          # Ansible configuration
├── deploy.yml                           # Main deployment playbook (THE SCRIPT TO RUN)
│
├── inventory/
│   ├── production.ini                   # [EDIT] Server inventory - your server details
│   └── production.ini.template          # Template reference
│
├── group_vars/
│   ├── production.yml                   # [EDIT] All deployment variables - your config
│   └── production.yml.template          # Template with all available options
│
├── Templates (Jinja2 - converted to actual config files):
│   ├── docker-compose.yml.j2            # Docker Compose services definition
│   ├── Caddyfile.j2                     # Reverse proxy + SSL configuration
│   ├── .env.j2                          # Environment variables for containers
│   └── init.sql                         # PostgreSQL initialization script
│
├── Documentation:
│   ├── QUICK_START.md                   # ⭐ Start here - 5 minute setup
│   ├── README.md                        # Complete deployment guide
│   ├── DEPLOYMENT.md                    # Detailed workflow & troubleshooting
│   └── setup.sh                         # Helper script to initialize config
│
└── .env.example                         # Reference of all .env variables
```

## Deployment Process Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Check Docker Installation                                │
│    If not present → Install Docker + Docker Compose        │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Create Deployment User & Directories                     │
│    User: deploy / Home: /home/deploy                        │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Clone/Update Git Repository                              │
│    From: {{ project_repo }}                                 │
│    To: /home/deploy/dherta-ai-service                       │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Generate Configuration Files                             │
│    ├─ docker-compose.yml (from .j2 template)               │
│    ├─ Caddyfile (from .j2 template)                        │
│    ├─ .env (from .j2 template with group_vars)            │
│    └─ init.sql (copy)                                      │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Docker Registry Login (if configured)                    │
│    Pull credentials from group_vars                         │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Pull Docker Images                                       │
│    ├─ dherta-backend:latest                                │
│    └─ dherta-frontend:latest                               │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Run Setup Profile                                        │
│    ├─ Download Paddle OCR models (~2GB)                    │
│    ├─ Download Playwright browsers (~1.5GB)                │
│    └─ Run any database migrations                          │
│    ⏱️  Takes 15-30 minutes (one-time only)                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. Start Full Docker Compose Stack                          │
│    Starts all 10 services in dependency order              │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 9. Health Verification                                      │
│    Checks: API, Database, Redis, Kafka, MinIO              │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ ✅ DEPLOYMENT COMPLETE                                      │
│                                                             │
│ Application ready at:                                       │
│ • https://your-domain.com                                  │
│ • https://your-domain.com/api/docs                         │
└─────────────────────────────────────────────────────────────┘
```

## Quick Reference: Three Commands to Deploy

```bash
# 1. Configure (one time)
cd ansible
cp inventory/production.ini.template inventory/production.ini
cp group_vars/production.yml.template group_vars/production.yml
# Edit both files ^

# 2. Test
ansible all -i inventory/production.ini -m ping

# 3. Deploy
ansible-playbook deploy.yml
```

That's it! The playbook handles:
- ✅ Docker installation
- ✅ Repository cloning
- ✅ Configuration file generation
- ✅ Image pulling from registry
- ✅ Model/browser downloads
- ✅ Service startup
- ✅ Health verification

## Services Deployed

| Service | Role | Port | Image |
|---------|------|------|-------|
| PostgreSQL | Database with pgvector | 5432 | ankane/pgvector:latest |
| Redis | Cache & session store | 6379 | redis:7-alpine |
| Zookeeper | Kafka coordination | 2181 | confluentinc/cp-zookeeper |
| Kafka | Message queue | 9092 | confluentinc/cp-kafka |
| MinIO | S3 object storage | 9000 | minio/minio:latest |
| API | FastAPI backend | 8000 | dherta-backend:latest |
| Document Worker | Extraction worker | — | dherta-backend:latest |
| Questions Worker | Processing worker | — | dherta-backend:latest |
| Audit Worker | Logging worker | — | dherta-backend:latest |
| Frontend | Web UI | 3000 | dherta-frontend:latest |
| Caddy | Reverse proxy + SSL | 80, 443 | caddy:2-alpine |

**Total: 11 containers forming a complete microservices architecture**

## Configuration Variables

Edit `group_vars/production.yml` with:

### Required (Change These!)
| Variable | Purpose | Example |
|----------|---------|---------|
| `domain` | Your domain | yourdomain.com |
| `backend_image` | Docker image path | registry.com/backend:v1 |
| `frontend_image` | Docker image path | registry.com/frontend:v1 |
| `postgres_password` | Database password | securepwd123! |
| `minio_root_password` | MinIO password | securepwd123! |
| `llm_api_key` | Gemini/OpenAI API key | sk-... |
| `jwt_secret_key` | JWT signing secret | random-string-here |

### Optional (Sensible Defaults)
| Variable | Default | When to Change |
|----------|---------|-----------------|
| `enable_gpu` | true | Set to false if no NVIDIA GPU |
| `ocr_use_gpu` | true | GPU for document OCR |
| `llm_provider` | gemini | Change to "openai" if using OpenAI |
| `docker_registry` | your-registry.com | Your private Docker registry |

### All Variables Documented in
- `group_vars/production.yml.template` — Complete reference with comments
- `group_vars/production.yml` — Your actual configuration

## Key Features

### 🔄 Idempotent
Run the playbook multiple times — it's safe. Each task checks if work is needed.

### 🏷️ Modular with Tags
Deploy specific components:
```bash
ansible-playbook deploy.yml --tags docker,docker-compose  # Just infrastructure
ansible-playbook deploy.yml --tags config,deploy          # Update config & restart
ansible-playbook deploy.yml --tags images,deploy          # New images + restart
```

### 🔒 Production-Ready
- Uses HTTPS with automatic Let's Encrypt via Caddy
- Database passwords encrypted in transit
- Proper health checks and service dependencies
- Resource limits and restart policies

### 📊 Monitoring Built-In
- Health checks for PostgreSQL, Redis, Kafka, MinIO, API
- Container restart on failure
- Logging to stdout (captured by Docker)

### 🛡️ Security
- Dedicated `deploy` user (non-root)
- SSH key authentication
- Secrets in environment variables only
- No passwords in logs

## Deployment Scenarios

### Scenario 1: Fresh Deployment
```bash
ansible-playbook deploy.yml
```
Takes 30-45 minutes total. Installs everything from scratch.

### Scenario 2: Update Configuration
```bash
# Edit group_vars/production.yml, then:
ansible-playbook deploy.yml --tags config,deploy
```
Takes 2-3 minutes. Regenerates configs and restarts services.

### Scenario 3: New Images
```bash
# After pushing new images to registry:
ansible-playbook deploy.yml --tags images,deploy
```
Takes 5-10 minutes. Pulls latest and restarts.

### Scenario 4: Add to Existing Deployment
```bash
# If Docker already exists:
ansible-playbook deploy.yml --skip-tags docker,docker-compose
```
Skips Docker installation, proceeds with everything else.

### Scenario 5: Dry Run (Check First)
```bash
ansible-playbook deploy.yml --check
```
Shows what would happen without making changes.

## File Customization Guide

### To use a different database:
Edit `group_vars/production.yml`:
```yaml
postgres_user: myuser
postgres_db: my_database
```
Playbook regenerates `docker-compose.yml` automatically.

### To add environment variables:
Edit `templates/.env.j2` to add new variables, then:
```yaml
# In group_vars/production.yml:
my_new_var: "value"
```

### To modify Docker services:
Edit `docker-compose.yml.j2` — it's a standard Jinja2 template.
```jinja2
{% if enable_gpu %}
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
{% endif %}
```

### To change reverse proxy behavior:
Edit `Caddyfile.j2`:
```caddy
handle /custom/* {
    uri strip_prefix /custom
    reverse_proxy custom-service:9000
}
```

## Troubleshooting Quick Links

| Problem | Solution |
|---------|----------|
| SSH connection fails | Check `inventory/production.ini` — IP, username, key path |
| Docker not found | Run `ansible-playbook deploy.yml --tags docker` |
| Registry login fails | Verify `docker_username`/`docker_password` in group_vars |
| Setup hangs | Common with slow internet + large models; check logs |
| API won't start | SSH to server: `docker compose logs api` |
| Port 80/443 in use | `sudo ufw status` and check firewall rules |
| Disk space errors | Run `docker system df` to check container size |

Full troubleshooting guide: See [DEPLOYMENT.md](ansible/DEPLOYMENT.md)

## Post-Deployment

### Access Your Application
```bash
# Frontend
https://your-domain.com

# API with auto-generated docs
https://your-domain.com/api/docs

# MinIO S3 console (user: minioadmin)
https://your-domain.com/minio/
```

### Common Operations
```bash
# SSH to server
ssh ubuntu@your-server.com

# Check services
cd /home/deploy/dherta-ai-service/docker
docker compose ps

# View logs
docker compose logs -f api
docker compose logs -f document-worker

# Restart a service
docker compose restart api

# Update code and restart
cd /home/deploy/dherta-ai-service
git pull origin main
cd docker
docker compose restart api
```

## Maintenance

### Regular Tasks
- **Daily**: Check container health (`docker compose ps`)
- **Weekly**: Review logs for errors (`docker compose logs`)
- **Monthly**: Update images (`docker compose pull` and restart)
- **Quarterly**: Backup database and clean up old data

### Backup Database
```bash
docker compose exec postgres pg_dump -U postgres ai_service > backup.sql
```

### Clean Up
```bash
docker image prune -a         # Remove unused images
docker volume prune           # Remove unused volumes
docker system df              # Check what's taking space
```

## Documentation Files

| File | Purpose |
|------|---------|
| **QUICK_START.md** | ⭐ 5-minute setup guide — START HERE |
| **README.md** | Complete reference with all options |
| **DEPLOYMENT.md** | Workflow, checklists, and troubleshooting |
| **ansible.cfg** | Ansible behavior configuration |
| **deploy.yml** | The main playbook (what actually runs) |
| **setup.sh** | Helper to initialize config templates |
| **group_vars/production.yml.template** | Reference of all possible variables |

## Architecture Benefits

```
✓ One playbook for entire deployment
✓ Reproducible — deploy 10 identical servers
✓ Idempotent — safe to run multiple times
✓ Documented — every variable explained
✓ Modular — deploy just parts you need
✓ Tested — based on proven local Docker setup
✓ Secured — proper authentication, HTTPS, secrets handling
✓ Monitored — health checks and logging included
```

## Next Steps

1. **Read QUICK_START.md** (5 min)
2. **Copy templates** and edit for your environment (5 min)
3. **Test connectivity** with ansible ping (1 min)
4. **Run deployment** (30-45 min including model downloads)
5. **Verify** at https://your-domain.com

---

**Total Setup Time**: ~1 hour (including model downloads on first run)
**Future Deployments**: 20-30 minutes (models already cached)
**Manual Deployment Time**: 2-3 hours of error-prone steps — **Ansible saves you time!**

For questions, see the comprehensive documentation files in this directory.
