# 🐳 Docker Deployment Guide

This guide explains how to run Cold Outreach Copilot using Docker for easy deployment and consistent environments.

---

## 📋 Prerequisites

- **Docker Desktop** (Windows/Mac) or **Docker Engine** (Linux)
  - Download from: https://www.docker.com/products/docker-desktop
  - Minimum: Docker 20.10+ and Docker Compose 1.29+
- **8GB RAM** recommended (4GB minimum)
- **10GB free disk space** (for Docker images, models, and data)

---

## 🚀 Quick Start

### Windows

1. Open PowerShell or Command Prompt in the project directory
2. Run the setup script:
   ```cmd
   docker-setup.bat
   ```

### Linux/Mac

1. Open Terminal in the project directory
2. Make the script executable and run it:
   ```bash
   chmod +x docker-setup.sh
   ./docker-setup.sh
   ```

### Manual Setup (All Platforms)

```bash
# 1. Create .env file
cp .env.example .env

# 2. Create data directories
mkdir -p data/uploads data/scraped_content

# 3. Build and start containers
docker-compose up -d --build

# 4. Pull the Ollama model (first time only)
docker-compose --profile init up ollama-init
```

---

## 🌐 Access the Application

Once containers are running:

1. **Wait 30-60 seconds** for initialization (Playwright browsers, Streamlit startup)
2. Open your browser to: **http://localhost:8501**
3. Upload your resume and start generating outreach messages!

---

## 📦 What Gets Deployed

The Docker setup creates **2 main containers**:

### 1. `cold-outreach-app` (Streamlit App)
- Python application with Streamlit UI
- Playwright for web scraping
- SQLAlchemy for database
- Ports: `8501` (Streamlit)

### 2. `cold-outreach-ollama` (LLM Server)
- Ollama server for running local AI models
- Qwen3 4B model for message generation
- Ports: `11434` (Ollama API)

### 3. `cold-outreach-ollama-init` (Optional)
- One-time service to download the AI model
- Only runs when using `--profile init`

---

## 📂 Data Persistence

Data is stored in **Docker volumes** and **local directories**:

| Location | Purpose | Persistence |
|----------|---------|-------------|
| `./data/` | Database, uploads, scraped content | **Persisted** (survives restarts) |
| `ollama_data` | Downloaded AI models | **Persisted** (Docker volume) |
| `app_cache` | Playwright cache, temp files | **Persisted** (Docker volume) |

**Important:** Your data is safe even if you stop/restart containers!

---

## 🛠️ Common Commands

### View Logs
```bash
# All services
docker-compose logs -f

# Just the app
docker-compose logs -f app

# Just Ollama
docker-compose logs -f ollama
```

### Stop the Application
```bash
docker-compose down
```

### Restart the Application
```bash
docker-compose restart
```

### Rebuild After Code Changes
```bash
docker-compose up -d --build
```

### Pull Latest Ollama Model
```bash
docker-compose --profile init up ollama-init
```

### Check Container Status
```bash
docker-compose ps
```

### Clean Up Everything (⚠️ Deletes data!)
```bash
# Stop and remove containers, volumes, and images
docker-compose down -v --rmi all

# Remove local data (optional)
rm -rf data/
```

---

## 🐛 Troubleshooting

### Issue: "Cannot connect to Ollama"
**Solution:**
```bash
# 1. Check if Ollama is running
docker-compose ps

# 2. Pull the model
docker-compose --profile init up ollama-init

# 3. Verify model is available
docker exec cold-outreach-ollama ollama list
```

### Issue: "Playwright browser not found"
**Solution:**
```bash
# Rebuild the container to reinstall browsers
docker-compose up -d --build --force-recreate app
```

### Issue: "Port 8501 already in use"
**Solution:**
```bash
# Option 1: Stop other Streamlit apps
pkill -f streamlit

# Option 2: Change port in docker-compose.yml
# Change "8501:8501" to "8502:8501" and access at localhost:8502
```

### Issue: Container keeps restarting
**Solution:**
```bash
# Check logs for errors
docker-compose logs -f app

# Common causes:
# - Missing .env file (create from .env.example)
# - Insufficient memory (allocate more RAM to Docker)
# - Corrupted volumes (remove with: docker-compose down -v)
```

### Issue: Slow performance
**Solution:**
- Allocate more resources in Docker Desktop settings:
  - **CPU:** 4+ cores recommended
  - **Memory:** 8GB+ recommended
  - **Swap:** 2GB+

---

## 🔧 Advanced Configuration

### Custom Environment Variables

Edit `.env` file to customize:

```bash
# Ollama Configuration
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=qwen3:4b-instruct

# Database
DATABASE_PATH=/app/data/outreach.db

# Scraping
SCRAPER_RATE_LIMIT=2
SCRAPER_CACHE_ENABLED=true
SCRAPER_TIMEOUT=30

# LLM
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000

# Logging
LOG_LEVEL=INFO
```

### Use Different AI Model

```bash
# 1. Pull a different model
docker exec cold-outreach-ollama ollama pull llama2:7b

# 2. Update .env
OLLAMA_MODEL=llama2:7b

# 3. Restart app
docker-compose restart app
```

### Run on Different Port

Edit `docker-compose.yml`:
```yaml
services:
  app:
    ports:
      - "8502:8501"  # Change 8502 to your desired port
```

### Enable GPU Acceleration (NVIDIA)

Add to `docker-compose.yml` under `ollama` service:
```yaml
ollama:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

---

## 🚀 Production Deployment

### Deploy to Cloud

#### AWS ECS / Azure Container Instances / Google Cloud Run

1. Build and push image to registry:
   ```bash
   docker build -t your-registry/cold-outreach:latest .
   docker push your-registry/cold-outreach:latest
   ```

2. Use `docker-compose.yml` as a template for cloud deployment

#### Docker Swarm

```bash
docker stack deploy -c docker-compose.yml cold-outreach
```

#### Kubernetes

Convert docker-compose to Kubernetes manifests:
```bash
kompose convert -f docker-compose.yml
kubectl apply -f .
```

### Reverse Proxy (Nginx/Traefik)

```nginx
server {
    listen 80;
    server_name outreach.yourdomain.com;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### HTTPS with Let's Encrypt

Use Traefik with Docker Compose for automatic SSL:
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.app.rule=Host(`outreach.yourdomain.com`)"
  - "traefik.http.routers.app.tls.certresolver=letsencrypt"
```

---

## 📊 Resource Usage

**Expected resource consumption:**

| Component | CPU | RAM | Disk |
|-----------|-----|-----|------|
| Streamlit App | 0.5-1 core | 1-2 GB | 500 MB |
| Ollama + Model | 2-4 cores | 4-6 GB | 3-5 GB |
| Total | ~3-5 cores | ~5-8 GB | ~4-6 GB |

**First-time setup:**
- **Build time:** 5-10 minutes
- **Model download:** 2-5 minutes (2-3 GB)
- **Total:** ~15 minutes

**Subsequent starts:**
- **Start time:** 10-30 seconds

---

## 🎓 Architecture

```
┌─────────────────────────────────────────────┐
│          Docker Compose Network             │
│                                             │
│  ┌───────────────┐      ┌───────────────┐  │
│  │               │      │               │  │
│  │   Streamlit   │─────▶│    Ollama     │  │
│  │      App      │ HTTP │    Server     │  │
│  │   (Port 8501) │      │  (Port 11434) │  │
│  │               │      │               │  │
│  └───────┬───────┘      └───────┬───────┘  │
│          │                      │          │
│          ▼                      ▼          │
│  ┌──────────────┐      ┌──────────────┐   │
│  │ ./data/      │      │ ollama_data  │   │
│  │ (Host Volume)│      │ (Volume)     │   │
│  └──────────────┘      └──────────────┘   │
└─────────────────────────────────────────────┘
```

---

## 📝 Next Steps

1. ✅ **Access the app** at http://localhost:8501
2. 📄 **Upload your resume** (PDF, DOCX, or TXT)
3. 🎯 **Configure target role** and message preferences
4. 🔍 **Enter company URLs** to generate personalized messages
5. 📊 **Track your outreach** in the CRM dashboard

---

## 🤝 Need Help?

- **Issues:** https://github.com/anthropics/claude-code/issues
- **Documentation:** README.md
- **Logs:** `docker-compose logs -f`

---

**Built with Docker ❤️**
