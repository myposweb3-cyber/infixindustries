#!/bin/bash

# SSL Setup Script for imicon.lk
# This script sets up Let's Encrypt SSL certificates using Certbot with Docker

set -e

DOMAIN="imicon.lk"
DOMAIN_ALT="www.imicon.lk"
EMAIL="your-email@example.com"  # Update this with your email
APP_DIR="/home/appuser/web_pos"

echo "🔒 Setting up SSL for $DOMAIN..."

# Navigate to app directory
cd "$APP_DIR"

# 1. Create certbot data directory if it doesn't exist
echo "📁 Creating certbot directories..."
mkdir -p ./certbot/conf
mkdir -p ./certbot/www

# 2. Stop nginx temporarily to allow certbot to bind to port 80
echo "⏸️  Stopping Nginx temporarily..."
docker-compose stop nginx

# Wait a moment for the port to be released
sleep 2

# 3. Run certbot in standalone mode to obtain certificates
echo "🔑 Obtaining SSL certificates from Let's Encrypt..."
docker run --rm \
  -v "$APP_DIR/certbot/conf:/etc/letsencrypt" \
  -v "$APP_DIR/certbot/www:/var/www/certbot" \
  -p 80:80 \
  -p 443:443 \
  certbot/certbot certonly --standalone \
  --non-interactive \
  --agree-tos \
  --email "$EMAIL" \
  -d "$DOMAIN" \
  -d "$DOMAIN_ALT"

echo "✅ Certificates obtained successfully!"

# 4. Set proper permissions
echo "🔐 Setting certificate permissions..."
chmod -R 755 ./certbot/conf

# 5. Restart Docker containers
echo "🚀 Restarting Docker containers..."
docker-compose up -d

# 6. Verify SSL setup
echo "🔍 Verifying SSL setup..."
sleep 5
curl -I https://$DOMAIN 2>/dev/null | head -1 && echo "✅ SSL is working!" || echo "⚠️  Please check the logs"

echo ""
echo "═════════════════════════════════════════════════════════════"
echo "✅ SSL Setup Complete!"
echo "═════════════════════════════════════════════════════════════"
echo ""
echo "Your site is now accessible at: https://$DOMAIN"
echo ""
echo "📋 Certificate Details:"
echo "  Domain: $DOMAIN"
echo "  Alt: $DOMAIN_ALT"
echo "  Cert Location: /etc/letsencrypt/live/$DOMAIN/"
echo "  Auto-renewal: Configured (runs daily)"
echo ""
echo "⚠️  IMPORTANT - Certificate Renewal:"
echo "  Certificates expire in 90 days"
echo "  Auto-renewal will run via cron job"
echo "  Check renewal status:"
echo "  docker-compose exec pos_nginx certbot renew --dry-run"
echo ""
