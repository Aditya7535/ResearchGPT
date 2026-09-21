# 🚀 ResearchGPT — Production Deployment Guide

This guide covers deploying ResearchGPT using **Docker & Docker Compose** as well as local developer workflows and cloud hosting platforms.

---

## 🏛️ Architecture Overview

ResearchGPT is containerized as a two-tier microservices architecture:

```
                          ┌──────────────────────────┐
                          │   Client Browser / User  │
                          └─────────────┬────────────┘
                                        │
                                        ▼ (Port 80)
               ┌─────────────────────────────────────────────────┐
               │         Frontend Container (Nginx Alpine)       │
               │                                                 │
               │  • Serves production React SPA bundle           │
               │  • Gzip compression & static asset caching      │
               │  • Reverse proxy: /api/* ──► http://backend:8000│
               └────────────────────────┬────────────────────────┘
                                        │
                                        ▼ (Port 8000)
               ┌─────────────────────────────────────────────────┐
               │           Backend Container (FastAPI)           │
               │                                                 │
               │  • LangGraph Multi-Agent Engine:                │
               │     Structuring ──► Citation ──► Formatting     │
               │  • Guided Interview Agent & Gap Analysis        │
               │  • Cosine Plagiarism Detection                  │
               │  • Document Assembly (python-docx + WeasyPrint) │
               └────────────┬─────────────────────────┬──────────┘
                            │                         │
                            ▼                         ▼
                  ┌─────────────────┐       ┌─────────────────┐
                  │ ChromaDB Volume │       │  Exports Volume │
                  │  /app/chroma    │       │  /app/exports   │
                  └─────────────────┘       └─────────────────┘
```

---

## ⚡ Quickstart: Deploy with Docker Compose

### 1. Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows / macOS) or Docker Engine + Docker Compose (Linux).
- Free Groq API Key from [console.groq.com](https://console.groq.com) (or local Ollama instance).

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and insert your API key:
```bash
cp .env.example .env
```

Edit `.env`:
```env
# Choose provider: "groq" (fast cloud LLM) or "ollama" (local offline)
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_your_actual_groq_api_key_here
GROQ_MODEL=llama-3.1-8b-instant

# Optional port overrides (defaults: 80 for web, 8000 for API)
FRONTEND_PORT=80
BACKEND_PORT=8000
```

### 3. Launch Containers
Run the build and start the containers in detached mode:
```bash
docker compose up --build -d
```

### 4. Verify Services
- **Web User Interface**: Open [http://localhost](http://localhost) in your browser.
- **FastAPI Interactive Docs (Swagger)**: Open [http://localhost:8000/docs](http://localhost:8000/docs).
- **Backend Health Check**:
  ```bash
  curl http://localhost:8000/api/health
  ```
  Expected output:
  ```json
  {
    "status": "healthy",
    "version": "1.0.0",
    "llm_provider": "groq",
    "groq_configured": true,
    "chroma_connected": true,
    "chroma_chunk_count": 0
  }
  ```

### 5. Managing Containers
- **View live logs**:
  ```bash
  docker compose logs -f
  ```
- **Stop containers**:
  ```bash
  docker compose down
  ```
- **Stop and remove persistent vector data**:
  ```bash
  docker compose down -v
  ```

---

## 💻 Local Development Setup (Without Docker)

If you prefer running services directly on your host machine for development:

### 1. Backend (FastAPI)
```bash
# 1. Create and activate a virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Set environment variables
export GROQ_API_KEY="gsk_your_key_here"
export LLM_PROVIDER="groq"

# 4. Start the FastAPI development server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Frontend (React + Vite)
```bash
cd frontend

# 1. Install Node dependencies
npm install

# 2. Start Vite dev server (automatically proxies /api to http://localhost:8000)
npm run dev
```
Open [http://localhost:3000](http://localhost:3000).

---

## ☁️ Cloud Deployment Options

### Option A: Single VPS / Cloud VM (DigitalOcean / Linode / AWS EC2 / GCP Compute)
1. Provision an Ubuntu 22.04 / 24.04 LTS instance (2+ vCPUs, 4GB+ RAM recommended for embeddings and PDF compiling).
2. Install Docker & Docker Compose:
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-v2
   sudo usermod -aG docker $USER
   ```
3. Clone your repository:
   ```bash
   git clone <your-repo-url> ResearchGPT
   cd ResearchGPT
   cp .env.example .env
   # Edit .env with your credentials
   docker compose up --build -d
   ```
4. Configure firewall / security group to allow inbound traffic on port `80` (HTTP) and `443` (HTTPS).
5. (Optional) Run Certbot with Nginx for automatic SSL:
   ```bash
   sudo apt install -y certbot python3-certbot-nginx
   ```

### Option B: Managed Containers (Render — Recommended Free Tier)

Render provides a generous free tier that supports both the Python/Docker backend and the React frontend static site.

#### Step 1: Push Code to GitHub
Ensure your repository is on GitHub:
```bash
# Initialize git if not already done
git init
git add .
git commit -m "feat: configure ResearchGPT for cloud deployment"
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/ResearchGPT.git
git push -u origin main
```

#### Step 2: Deploy Using Render Blueprint (`render.yaml`)
1. Log in to [dashboard.render.com](https://dashboard.render.com).
2. Click **New +** ➔ **Blueprint**.
3. Connect your GitHub repository `ResearchGPT`.
4. Render will detect `render.yaml` and create two services:
   - **`researchgpt-backend`**: Docker Web Service running `Dockerfile.backend`.
   - **`researchgpt-frontend`**: Static Site building the React SPA.
5. In the environment parameters prompt, enter your **`GROQ_API_KEY`** (get one free at [console.groq.com](https://console.groq.com)).
6. Click **Apply**.
7. Once the backend builds, copy its live URL (e.g. `https://researchgpt-backend.onrender.com`).
8. Go to the frontend service settings on Render ➔ **Environment Variables** ➔ set `VITE_API_BASE_URL` to `https://researchgpt-backend.onrender.com`. Trigger a manual deploy of the frontend.

#### Step 3 (Alternative): Manual Setup on Render
- **Backend (Web Service)**:
  - Select **New +** ➔ **Web Service** ➔ connect repo.
  - Runtime: **Docker** (Dockerfile Path: `Dockerfile.backend`).
  - Plan: **Free**.
  - Add Environment Variables:
    - `LLM_PROVIDER`: `groq`
    - `GROQ_API_KEY`: `gsk_your_groq_key`
    - `GROQ_MODEL`: `llama-3.1-8b-instant`
- **Frontend (Static Site)**:
  - Select **New +** ➔ **Static Site** ➔ connect repo.
  - Root Directory: `frontend`
  - Build Command: `npm install && npm run build`
  - Publish Directory: `dist`
  - Environment Variable: `VITE_API_BASE_URL` = `https://<your-backend>.onrender.com`

---

### Option C: Managed Containers on Railway

1. Go to [railway.com](https://railway.com) and log in with GitHub.
2. Click **New Project** ➔ **Deploy from GitHub repo** ➔ choose `ResearchGPT`.
3. Railway will build the backend using `Dockerfile.backend` (configured in `railway.json`).
4. In Railway Settings ➔ **Variables**, add:
   - `GROQ_API_KEY`: `your_groq_key`
   - `LLM_PROVIDER`: `groq`
5. In Railway Settings ➔ **Networking**, click **Generate Domain** to get a public HTTPS URL.
6. For the frontend: Add another service from repo with root directory `frontend`, set `VITE_API_BASE_URL` to the backend Railway URL.

---

### Option D: Google Cloud Run
1. Build and push backend image to Artifact Registry:
   ```bash
   gcloud builds submit --tag gcr.io/[PROJECT-ID]/researchgpt-backend -f Dockerfile.backend
   ```
2. Deploy to Cloud Run:
   ```bash
   gcloud run deploy researchgpt-backend \
     --image gcr.io/[PROJECT-ID]/researchgpt-backend \
     --platform managed \
     --set-env-vars GROQ_API_KEY="your-key",LLM_PROVIDER="groq" \
     --allow-unauthenticated
   ```

---

## 🛡️ Production Checklist

- [x] CORS configured for production security in `app/main.py`.
- [x] Multi-stage build for frontend minimising Docker image size.
- [x] Caching and gzip compression enabled in Nginx.
- [x] WeasyPrint C-libraries pre-installed in Linux backend container.
- [x] Vector store (`chroma_data`) volume-mounted for data durability.
- [x] Resilient frontend with automatic fallbacks for offline mode.
- [x] Complete REST API with Swagger documentation at `/docs`.
