@echo off
REM Cold Outreach Copilot - Docker Setup Script for Windows
echo ========================================
echo Cold Outreach Copilot - Docker Setup
echo ========================================
echo.

REM Check if Docker is installed
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not installed or not in PATH
    echo Please install Docker Desktop from: https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

echo [1/5] Docker detected
echo.

REM Check if docker-compose is available
docker-compose --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] docker-compose is not installed
    echo Please ensure Docker Desktop is properly installed
    pause
    exit /b 1
)

echo [2/5] docker-compose detected
echo.

REM Create .env file if it doesn't exist
if not exist .env (
    echo [3/5] Creating .env file from .env.example...
    copy .env.example .env
    echo Created .env file. You can customize it if needed.
) else (
    echo [3/5] .env file already exists
)
echo.

REM Create data directories
echo [4/5] Creating data directories...
if not exist data mkdir data
if not exist data\uploads mkdir data\uploads
if not exist data\scraped_content mkdir data\scraped_content
echo Data directories created
echo.

echo [5/5] Building and starting Docker containers...
echo This may take 5-10 minutes on first run (downloading images, installing browsers)
echo.
docker-compose up -d --build

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo SUCCESS! Cold Outreach Copilot is running
    echo ========================================
    echo.
    echo The app is starting up. Please wait 30-60 seconds for initialization.
    echo.
    echo Access the app at: http://localhost:8501
    echo.
    echo To pull the Ollama model (required for first use):
    echo   docker-compose --profile init up ollama-init
    echo.
    echo Useful commands:
    echo   View logs:      docker-compose logs -f app
    echo   Stop app:       docker-compose down
    echo   Restart app:    docker-compose restart
    echo   Rebuild app:    docker-compose up -d --build
    echo.
) else (
    echo.
    echo [ERROR] Docker setup failed
    echo Check the error messages above
)

pause
