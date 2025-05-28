# SPX Straddle Calculator - LXC Container Deployment Guide

## 🚀 Quick Deployment on LXC Container

This guide will help you deploy the SPX Straddle Calculator on an LXC container.

### 📋 Prerequisites

**LXC Container Requirements:**
- Ubuntu 20.04+ or Debian 11+ LXC container
- At least 2GB RAM and 10GB storage
- Internet connectivity
- Root or sudo access

### 🔧 Step 1: Prepare LXC Container

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install required system packages
sudo apt install -y git curl wget software-properties-common apt-transport-https ca-certificates gnupg lsb-release

# Install Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Start and enable Docker
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group (replace 'username' with your actual username)
sudo usermod -aG docker $USER

# Log out and back in, or run:
newgrp docker
```

### 📥 Step 2: Clone Repository

```bash
# Clone the repository (replace with your actual repository URL)
git clone https://github.com/yourusername/spx-straddle-calculator.git spxstraddle
cd spxstraddle

# Verify files are present
ls -la
```

### ⚙️ Step 3: Configure Environment

```bash
# Copy environment template
cp env.example .env

# Edit configuration (use nano, vim, or your preferred editor)
nano .env
```

**Required Configuration in `.env`:**
```bash
# Polygon.io API Configuration (REQUIRED)
POLYGON_API_KEY=your_polygon_api_key_here

# Discord Configuration (OPTIONAL)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN
DISCORD_ENABLED=true

# Redis Configuration
REDIS_URL=redis://redis:6379

# API Server Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Logging Configuration
LOG_LEVEL=INFO

# Scheduler Configuration
ENABLE_SCHEDULER=true
CALCULATION_TIME=09:32  # Time in ET to run daily calculation
CLEANUP_DAY=sunday      # Day of week for cleanup
CLEANUP_TIME=02:00      # Time for cleanup

# Data Retention
KEEP_DAYS=90           # Number of days to keep historical data

# Market Configuration
MARKET_TIMEZONE=US/Eastern
SPX_TICKER=I:SPX
```

### 🐳 Step 4: Deploy with Docker Compose

**Option A: API Server Only**
```bash
# Run just the API server and Redis
docker-compose up -d
```

**Option B: Full System with Automated Scheduler**
```bash
# Run the complete system with daily automation
docker-compose --profile scheduler up -d
```

**Option C: Test Run**
```bash
# Run example usage to test everything
docker-compose --profile example up
```

### 🔍 Step 5: Verify Deployment

```bash
# Check container status
docker-compose ps

# Check logs
docker-compose logs -f

# Test API health
curl http://localhost:8000/health

# Test Discord webhook (if configured)
curl -X POST http://localhost:8000/api/discord/test

# View web dashboard
curl http://localhost:8000/api/spx-straddle/dashboard
```

### 🌐 Step 6: Access from Outside LXC Container

**If you want to access from your host machine:**

1. **Find LXC container IP:**
```bash
# Inside LXC container
hostname -I
```

2. **Access from host:**
```bash
# Replace <LXC_IP> with the actual IP
curl http://<LXC_IP>:8000/health
```

3. **Or set up port forwarding in LXC config** (on host):
```bash
# Add to LXC container config
lxc config device add <container-name> api-port proxy listen=tcp:0.0.0.0:8000 connect=tcp:127.0.0.1:8000
```

### 📊 Step 7: Monitor and Manage

```bash
# View real-time logs
docker-compose logs -f spx-scheduler

# Stop system
docker-compose down

# Restart system
docker-compose restart

# Update system (after git pull)
docker-compose down
git pull
docker-compose up --build -d

# View container resource usage
docker stats
```

### 🔧 Troubleshooting

**Common Issues:**

1. **Permission Denied for Docker:**
```bash
sudo usermod -aG docker $USER
newgrp docker
```

2. **Port Already in Use:**
```bash
# Check what's using port 8000
sudo lsof -i :8000
# Kill process or change API_PORT in .env
```

3. **Container Won't Start:**
```bash
# Check logs for errors
docker-compose logs spx-api
docker-compose logs spx-scheduler
```

4. **Discord Webhook Not Working:**
```bash
# Test webhook URL manually
curl -X POST -H "Content-Type: application/json" \
  -d '{"content":"Test message"}' \
  YOUR_DISCORD_WEBHOOK_URL
```

### 🚀 Production Recommendations

**For Production Deployment:**

1. **Use a reverse proxy (nginx):**
```bash
sudo apt install nginx
# Configure nginx to proxy to localhost:8000
```

2. **Set up SSL/TLS:**
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx
```

3. **Configure firewall:**
```bash
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

4. **Set up log rotation:**
```bash
# Add to /etc/logrotate.d/spx-straddle
/path/to/spxstraddle/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
}
```

5. **Monitor with systemd (optional):**
```bash
# Create systemd service for auto-restart
sudo nano /etc/systemd/system/spx-straddle.service
```

### 📈 What Happens Next

Once deployed, the system will:

1. **🕘 Daily at 9:32 AM ET**: Automatically calculate SPX straddle costs
2. **💬 Discord Notifications**: Send results to your Discord channel
3. **📊 Web Dashboard**: Available at `http://your-lxc-ip:8000/api/spx-straddle/dashboard`
4. **📈 API Access**: Full REST API for integration
5. **🧹 Weekly Cleanup**: Automatic data maintenance

### 🆘 Support

If you encounter issues:
1. Check container logs: `docker-compose logs -f`
2. Verify environment variables: `cat .env`
3. Test network connectivity: `curl http://localhost:8000/health`
4. Check Discord webhook: `curl -X POST http://localhost:8000/api/discord/test`

---

**🎉 Your SPX Straddle Calculator is now running on LXC!** 