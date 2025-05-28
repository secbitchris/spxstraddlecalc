#!/bin/bash

# SPX Straddle Calculator - LXC Deployment Script
# This script automates the deployment process on an LXC container

set -e  # Exit on any error

echo "🚀 SPX Straddle Calculator - LXC Deployment"
echo "============================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_warning "This script should not be run as root. Please run as a regular user with sudo privileges."
   exit 1
fi

# Step 1: Update system
print_step "1. Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Step 2: Install dependencies
print_step "2. Installing required packages..."
sudo apt install -y git curl wget software-properties-common apt-transport-https ca-certificates gnupg lsb-release

# Step 3: Install Docker
print_step "3. Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt update
    sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    
    # Start and enable Docker
    sudo systemctl start docker
    sudo systemctl enable docker
    
    # Add user to docker group
    sudo usermod -aG docker $USER
    print_status "Docker installed successfully!"
    print_warning "You may need to log out and back in for Docker group permissions to take effect."
else
    print_status "Docker is already installed."
fi

# Step 4: Verify Docker installation
print_step "4. Verifying Docker installation..."
if docker --version &> /dev/null; then
    print_status "Docker is working correctly."
else
    print_error "Docker installation failed or user needs to be added to docker group."
    print_warning "Try running: newgrp docker"
    exit 1
fi

# Step 5: Check if we're in the right directory
if [[ ! -f "docker-compose.yml" ]]; then
    print_error "docker-compose.yml not found. Please run this script from the spxstraddle directory."
    exit 1
fi

# Step 6: Set up environment file
print_step "5. Setting up environment configuration..."
if [[ ! -f ".env" ]]; then
    cp env.example .env
    print_status "Created .env file from template."
    print_warning "Please edit .env file with your configuration:"
    print_warning "  - Add your Polygon.io API key"
    print_warning "  - Add your Discord webhook URL (optional)"
    print_warning "  - Adjust other settings as needed"
    echo ""
    echo "Would you like to edit the .env file now? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        ${EDITOR:-nano} .env
    fi
else
    print_status ".env file already exists."
fi

# Step 7: Choose deployment option
print_step "6. Choose deployment option:"
echo "1) API Server Only (web dashboard + API)"
echo "2) Full System with Scheduler (automated daily calculations)"
echo "3) Test Run (run example to verify everything works)"
echo ""
echo -n "Enter your choice (1-3): "
read -r choice

case $choice in
    1)
        print_step "7. Deploying API Server Only..."
        docker-compose up -d
        ;;
    2)
        print_step "7. Deploying Full System with Scheduler..."
        docker-compose --profile scheduler up -d
        ;;
    3)
        print_step "7. Running Test Example..."
        docker-compose --profile example up
        ;;
    *)
        print_error "Invalid choice. Exiting."
        exit 1
        ;;
esac

# Step 8: Verify deployment
print_step "8. Verifying deployment..."
sleep 5

# Check container status
print_status "Container status:"
docker-compose ps

# Test API health
print_step "9. Testing API health..."
if curl -s http://localhost:8000/health > /dev/null; then
    print_status "✅ API is responding correctly!"
else
    print_warning "⚠️  API health check failed. Check logs with: docker-compose logs"
fi

# Final instructions
echo ""
echo "🎉 Deployment Complete!"
echo "======================"
print_status "Your SPX Straddle Calculator is now running!"
echo ""
echo "📊 Web Dashboard: http://$(hostname -I | awk '{print $1}'):8000/api/spx-straddle/dashboard"
echo "📚 API Documentation: http://$(hostname -I | awk '{print $1}'):8000/docs"
echo "🔍 Health Check: http://$(hostname -I | awk '{print $1}'):8000/health"
echo ""
echo "📋 Useful Commands:"
echo "  View logs:           docker-compose logs -f"
echo "  Stop system:         docker-compose down"
echo "  Restart system:      docker-compose restart"
echo "  Update system:       git pull && docker-compose up --build -d"
echo ""

if [[ $choice -eq 2 ]]; then
    print_status "🕘 Automated scheduler is running!"
    print_status "Daily calculations will run at 9:32 AM ET (weekdays only)"
    print_status "Discord notifications will be sent automatically"
fi

print_status "For troubleshooting, see LXC_DEPLOYMENT.md" 