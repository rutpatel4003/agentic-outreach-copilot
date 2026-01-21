#!/bin/bash
# Cold Outreach Copilot - Docker Setup Script for Linux/Mac

set -e  # Exit on error

echo "========================================"
echo "Cold Outreach Copilot - Docker Setup"
echo "========================================"
echo

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker is not installed"
    echo "Please install Docker from: https://docs.docker.com/get-docker/"
    exit 1
fi

echo "[1/5] ✓ Docker detected"
echo

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "[ERROR] docker-compose is not installed"
    echo "Please install docker-compose from: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "[2/5] ✓ docker-compose detected"
echo

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "[3/5] Creating .env file from .env.example..."
    cp .env.example .env
    echo "✓ Created .env file. You can customize it if needed."
else
    echo "[3/5] ✓ .env file already exists"
fi
echo

# Create data directories
echo "[4/5] Creating data directories..."
mkdir -p data/uploads data/scraped_content
echo "✓ Data directories created"
echo

echo "[5/5] Building and starting Docker containers..."
echo "This may take 5-10 minutes on first run (downloading images, installing browsers)"
echo

docker-compose up -d --build

echo
echo "========================================"
echo "SUCCESS! Cold Outreach Copilot is running"
echo "========================================"
echo
echo "The app is starting up. Please wait 30-60 seconds for initialization."
echo
echo "Access the app at: http://localhost:8501"
echo
echo "To pull the Ollama model (required for first use):"
echo "  docker-compose --profile init up ollama-init"
echo
echo "Useful commands:"
echo "  View logs:      docker-compose logs -f app"
echo "  Stop app:       docker-compose down"
echo "  Restart app:    docker-compose restart"
echo "  Rebuild app:    docker-compose up -d --build"
echo
