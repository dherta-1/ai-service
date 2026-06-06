#!/bin/bash
set -e

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║   Dherta AI Service - Ansible Deployment Setup Script        ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Check if Ansible is installed
if ! command -v ansible-playbook &> /dev/null; then
    echo "❌ Ansible is not installed."
    echo "Install it with: pip install ansible"
    exit 1
fi

echo "✓ Ansible version: $(ansible --version | head -n1)"
echo ""

# Create config from templates if they don't exist
echo "Setting up configuration files..."

if [ ! -f inventory/production.ini ]; then
    echo "Creating inventory/production.ini from template..."
    cp inventory/production.ini.template inventory/production.ini
    echo "⚠️  Please edit inventory/production.ini with your server details"
fi

if [ ! -f group_vars/production.yml ]; then
    echo "Creating group_vars/production.yml from template..."
    cp group_vars/production.yml.template group_vars/production.yml
    echo "⚠️  Please edit group_vars/production.yml with your configuration"
fi

echo ""
echo "Configuration Setup Complete!"
echo ""
echo "Next steps:"
echo "1. Edit inventory/production.ini with your server IP/hostname"
echo "2. Edit group_vars/production.yml with your configuration:"
echo "   - domain name"
echo "   - Docker registry credentials"
echo "   - Database passwords"
echo "   - LLM API key"
echo "   - SMTP settings"
echo ""
echo "3. Test connectivity:"
echo "   ansible all -i inventory/production.ini -m ping"
echo ""
echo "4. Review what will be deployed:"
echo "   ansible-playbook deploy.yml --check"
echo ""
echo "5. Run full deployment:"
echo "   ansible-playbook deploy.yml"
echo ""
echo "For more details, see README.md or DEPLOYMENT.md"
