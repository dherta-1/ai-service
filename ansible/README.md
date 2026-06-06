# Ansible Deployment Guide for Dherta AI Service

This directory contains Ansible playbooks and templates to deploy the Dherta AI Service to production environments.

## Overview

The deployment process consists of these steps:

1. **Docker Installation** — Check if Docker is installed, install if not
2. **Docker Compose Setup** — Install docker-compose plugin
3. **User & Directory Setup** — Create deployment user and directories
4. **Repository Clone** — Clone or update the project from git
5. **Configuration Generation** — Generate docker-compose.yml, Caddyfile, and .env from templates
6. **Image Registry Login** — Authenticate with Docker registry (if configured)
7. **Image Pull** — Pull backend and frontend images
8. **Setup Profile** — Run docker compose with setup profile to download models and browsers
9. **Service Startup** — Start the full Docker Compose stack
10. **Health Verification** — Verify API health endpoint
11. **Summary** — Display deployment completion details

## Prerequisites

### Local Machine
- Ansible installed (`pip install ansible`)
- SSH access to target server with sudo privileges
- Git installed on target server

### Target Server
- Ubuntu 20.04 LTS or later
- SSH server running
- User with sudo privileges (recommended: ubuntu user)
- At least 50GB free disk space for models and containers
- NVIDIA drivers installed (if using GPU for OCR workers)

## Quick Start

### 1. Configure Inventory and Variables

#### Copy template files:
```bash
cp inventory/production.ini.template inventory/production.ini
cp group_vars/production.yml.template group_vars/production.yml
```

#### Update `inventory/production.ini`:
```ini
[production]
your_server.com ansible_host=123.45.67.89 ansible_user=ubuntu ansible_ssh_private_key_file=~/.ssh/id_rsa

[production:vars]
ansible_python_interpreter=/usr/bin/python3
```

#### Update `group_vars/production.yml`:
```yaml
# Essential variables to change:
domain: your-domain.com
docker_registry: your-registry.com
docker_username: your-registry-user
docker_password: your-registry-password
backend_image: your-registry.com/dherta-backend:latest
frontend_image: your-registry.com/dherta-frontend:latest

# Database credentials (change from defaults!)
postgres_password: your-secure-password
minio_root_password: your-minio-password

# LLM Configuration
llm_api_key: your-gemini-or-openai-key

# JWT and security
jwt_secret_key: your-secure-jwt-secret

# SMTP for email notifications
smtp_username: your-email@gmail.com
smtp_password: your-app-password
```

### 2. Verify Connectivity

```bash
ansible all -i inventory/production.ini -m ping
```

Expected output:
```
your_server.com | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

### 3. Run the Deployment Playbook

```bash
ansible-playbook deploy.yml
```

To run specific tags (Docker installation only, for example):
```bash
ansible-playbook deploy.yml --tags docker
```

Available tags:
- `docker` — Docker installation only
- `docker-compose` — Docker Compose installation only
- `git` — Repository clone/update only
- `config` — Generate configuration files from templates
- `registry` — Docker registry login
- `images` — Pull Docker images
- `setup` — Run setup profile (download models)
- `deploy` — Start services
- `verify` — Health checks

### 4. Deployment Options

#### Deploy specific components:
```bash
# Only install Docker and Docker Compose
ansible-playbook deploy.yml --tags docker,docker-compose

# Only update configuration and restart services
ansible-playbook deploy.yml --tags config,deploy

# Full deployment with setup
ansible-playbook deploy.yml
```

#### Watch logs during deployment:
```bash
ansible-playbook deploy.yml -vvv
```

#### Dry run (check what would happen):
```bash
ansible-playbook deploy.yml --check
```

## Configuration Files

### Templates Used

#### `docker-compose.yml.j2`
- Generates the complete Docker Compose configuration
- Variables:
  - `postgres_user`, `postgres_password`, `postgres_db`
  - `minio_root_user`, `minio_root_password`
  - `backend_image`, `frontend_image`
  - `domain`
  - `enable_gpu` (enables NVIDIA device mapping for GPU workers)
  - `paddle_model_cache`, `playwright_cache` (model directories)

#### `Caddyfile.j2`
- Generates reverse proxy configuration
- Serves API, Storage, and Frontend through single domain
- Automatic HTTPS via Caddy

#### `.env.j2`
- Generates runtime environment variables for containers
- Populated from group variables in `group_vars/production.yml`
- Includes:
  - Database credentials
  - S3/MinIO settings
  - LLM configuration
  - JWT secrets
  - CORS settings

### Important Security Notes

1. **Change Defaults**: Update all passwords and secrets in `group_vars/production.yml`
2. **Protect Credentials**: Don't commit actual credentials to version control
3. **SSH Keys**: Use SSH key authentication (recommended) instead of passwords
4. **JWT Secret**: Use a strong random secret for `jwt_secret_key`
5. **.env File**: The generated `.env` file contains secrets—keep it secure with mode `0600`

## Post-Deployment

### Access Your Application

```bash
# Frontend: https://your-domain.com
# API: https://your-domain.com/api
# MinIO Console: https://your-domain.com/minio/
# API Docs: https://your-domain.com/api/docs
```

### Common Operations

#### Check service status:
```bash
ssh ubuntu@your-server.com
cd /home/deploy/dherta-ai-service/docker
docker compose ps
```

#### View logs:
```bash
docker compose logs -f api          # API logs
docker compose logs -f document-worker  # Document extraction worker
docker compose logs -f questions-worker # Question extraction worker
```

#### Restart services:
```bash
docker compose restart api
docker compose restart document-worker
```

#### Update and redeploy:
```bash
# Update code from git
cd /home/deploy/dherta-ai-service
git pull origin main

# Regenerate configs and restart
cd docker
docker compose pull
docker compose up -d
```

## Troubleshooting

### Docker not found
If Docker installation fails:
```bash
# SSH to server and check manually
ssh ubuntu@your-server.com
sudo apt-get update
sudo apt-get install docker.io
sudo usermod -aG docker deploy
```

### Images failed to pull
```bash
# Check registry credentials
docker login your-registry.com

# Manually pull
docker pull your-registry.com/dherta-backend:latest
```

### Setup profile hangs
If model download hangs (common with large models):
```bash
# Set timeout in ansible
ansible-playbook deploy.yml --tags setup -e 'ansible_async_dir=/tmp/.ansible_async'
```

### Services won't start
```bash
# Check logs
docker compose logs setup
docker compose logs api

# Verify environment variables
docker compose config

# Check disk space
docker system df
```

### API health check fails
```bash
# SSH to server and test directly
ssh ubuntu@your-server.com
curl http://localhost:8000/health
docker compose logs api
```

## Directory Structure

```
ansible/
├── ansible.cfg                     # Ansible configuration
├── deploy.yml                      # Main deployment playbook
├── README.md                       # This file
├── inventory/
│   ├── production.ini              # Production inventory (edit this)
│   └── production.ini.template     # Template (reference)
├── group_vars/
│   ├── production.yml              # Production variables (edit this)
│   └── production.yml.template     # Template (reference)
├── docker-compose.yml.j2           # Docker Compose template
├── Caddyfile.j2                    # Caddy reverse proxy template
├── .env.j2                         # Environment variables template
├── .env.example                    # Example .env for reference
└── init.sql                        # PostgreSQL initialization script
```

## Advanced Configuration

### Using Private Docker Registry

In `group_vars/production.yml`:
```yaml
docker_registry: registry.company.com
docker_username: my-user
docker_password: my-password
backend_image: registry.company.com/my-org/dherta-backend:latest
frontend_image: registry.company.com/my-org/dherta-frontend:latest
```

### Disabling GPU Support

If your server doesn't have NVIDIA GPU:
```yaml
enable_gpu: false
```

### Custom Domain with SSL

Caddy automatically handles SSL. Just ensure:
1. Domain DNS points to server
2. Port 80 and 443 are accessible
3. Email for Let's Encrypt is configured

### Custom Model Paths

```yaml
paddle_model_cache: /data/models/paddle
playwright_cache: /data/models/browsers
```

### Environment-specific Variables

Create separate files for different environments:
```bash
group_vars/staging.yml
group_vars/production.yml
inventory/staging.ini
inventory/production.ini
```

Then run:
```bash
ansible-playbook deploy.yml -i inventory/staging.ini
```

## Rollback & Cleanup

### Stop all services:
```bash
docker compose down
```

### Remove volumes and data:
```bash
docker compose down -v
```

### View deployment history:
```bash
git log --oneline  # In the cloned repository
```

## Getting Help

For issues:
1. Check logs: `docker compose logs -f`
2. Run with verbose mode: `ansible-playbook deploy.yml -vvv`
3. SSH to server and debug manually
4. Check Ansible documentation: https://docs.ansible.com

## Next Steps

- Configure GitHub Actions or GitLab CI for automatic deployments
- Set up monitoring and alerting (Prometheus, Grafana)
- Configure automated backups for PostgreSQL data
- Set up log aggregation (ELK Stack, Loki)
- Implement CI/CD pipeline for image builds
