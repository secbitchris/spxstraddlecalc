#!/bin/bash

# SPX Straddle Calculator Startup Script
# This script provides easy commands to start the application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if .env file exists
check_env_file() {
    if [ ! -f .env ]; then
        print_warning ".env file not found. Creating from template..."
        if [ -f env.example ]; then
            cp env.example .env
            print_warning "Please edit .env file with your API keys before continuing"
            exit 1
        else
            print_error "env.example file not found!"
            exit 1
        fi
    fi
}

# Function to check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
}

# Function to check if Python dependencies are installed
check_python_deps() {
    if [ ! -d "venv" ] && [ ! -d ".venv" ]; then
        print_warning "Virtual environment not found. Creating one..."
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
        print_success "Virtual environment created and dependencies installed"
    fi
}

# Function to start with Docker
start_docker() {
    print_status "Starting SPX Straddle Calculator with Docker..."
    check_docker
    check_env_file
    
    case $1 in
        "api")
            print_status "Starting API server only..."
            docker-compose up spx-api redis
            ;;
        "scheduler")
            print_status "Starting with scheduler..."
            docker-compose --profile scheduler up
            ;;
        "example")
            print_status "Running example usage..."
            docker-compose --profile example up spx-example
            ;;
        *)
            print_status "Starting API server and Redis..."
            docker-compose up
            ;;
    esac
}

# Function to start locally
start_local() {
    print_status "Starting SPX Straddle Calculator locally..."
    check_env_file
    check_python_deps
    
    # Activate virtual environment if it exists
    if [ -d "venv" ]; then
        source venv/bin/activate
    elif [ -d ".venv" ]; then
        source .venv/bin/activate
    fi
    
    # Check if Redis is running
    if ! redis-cli ping &> /dev/null; then
        print_warning "Redis is not running. Please start Redis first:"
        print_warning "  brew services start redis  # macOS"
        print_warning "  sudo systemctl start redis  # Linux"
        print_warning "  redis-server  # Manual start"
        exit 1
    fi
    
    case $1 in
        "api")
            print_status "Starting API server..."
            python api_server.py
            ;;
        "scheduler")
            print_status "Starting scheduler..."
            python scheduler.py
            ;;
        "example")
            print_status "Running example usage..."
            python example_usage.py
            ;;
        *)
            print_status "Starting API server..."
            python api_server.py
            ;;
    esac
}

# Function to show help
show_help() {
    echo "SPX Straddle Calculator Startup Script"
    echo ""
    echo "Usage: $0 [COMMAND] [SERVICE]"
    echo ""
    echo "Commands:"
    echo "  docker [SERVICE]  Start with Docker (recommended)"
    echo "  local [SERVICE]   Start locally (requires Redis)"
    echo "  setup            Setup environment and dependencies"
    echo "  logs             Show Docker logs"
    echo "  stop             Stop all Docker services"
    echo "  clean            Clean up Docker containers and volumes"
    echo "  test             Run tests"
    echo "  help             Show this help message"
    echo ""
    echo "Services (optional):"
    echo "  api              Start API server only"
    echo "  scheduler        Start with scheduler"
    echo "  example          Run example usage"
    echo ""
    echo "Examples:"
    echo "  $0 docker                # Start API + Redis with Docker"
    echo "  $0 docker scheduler      # Start with scheduler"
    echo "  $0 local api            # Start API locally"
    echo "  $0 setup                # Setup environment"
}

# Function to setup environment
setup_env() {
    print_status "Setting up SPX Straddle Calculator environment..."
    
    # Copy env file if needed
    if [ ! -f .env ]; then
        if [ -f env.example ]; then
            cp env.example .env
            print_success ".env file created from template"
        else
            print_error "env.example file not found!"
            exit 1
        fi
    fi
    
    # Create virtual environment for local development
    if [ ! -d "venv" ]; then
        print_status "Creating Python virtual environment..."
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
        print_success "Virtual environment created and dependencies installed"
    fi
    
    # Create logs directory
    mkdir -p logs
    
    print_success "Environment setup complete!"
    print_warning "Please edit .env file with your API keys:"
    print_warning "  - POLYGON_API_KEY (required)"
    print_warning "  - DISCORD_BOT_TOKEN (optional)"
    print_warning "  - DISCORD_CHANNEL_ID (optional)"
}

# Function to show logs
show_logs() {
    check_docker
    docker-compose logs -f
}

# Function to stop services
stop_services() {
    check_docker
    print_status "Stopping all services..."
    docker-compose down
    print_success "All services stopped"
}

# Function to clean up
clean_up() {
    check_docker
    print_status "Cleaning up Docker containers and volumes..."
    docker-compose down -v
    docker system prune -f
    print_success "Cleanup complete"
}

# Function to run tests
run_tests() {
    print_status "Running tests..."
    check_env_file
    
    if [ -d "venv" ]; then
        source venv/bin/activate
    elif [ -d ".venv" ]; then
        source .venv/bin/activate
    fi
    
    python example_usage.py
    print_success "Tests completed"
}

# Main script logic
case $1 in
    "docker")
        start_docker $2
        ;;
    "local")
        start_local $2
        ;;
    "setup")
        setup_env
        ;;
    "logs")
        show_logs
        ;;
    "stop")
        stop_services
        ;;
    "clean")
        clean_up
        ;;
    "test")
        run_tests
        ;;
    "help"|"--help"|"-h")
        show_help
        ;;
    "")
        print_status "No command specified. Starting with Docker..."
        start_docker
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac 