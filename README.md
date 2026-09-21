# 🔬 ResearchGPT

> **Autonomous Multi-Agent Academic Paper Analysis, Fact-Checked Citation Tracking, and Publication-Ready Document Assembly.**

---

## ✨ Features

- **Multi-Agent LangGraph Pipeline**:
  - **Structuring Agent**: Analyzes uploaded papers, generates structured thesis outlines, and drafts core academic sections.
  - **Citation Agent**: Fact-checks assertions against ChromaDB embeddings, looks up CrossRef DOIs, and formats publication-compliant bibliographies (APA, Vancouver, IEEE).
  - **Formatting Agent**: Enforces university templates, verifies section hierarchy, and compiles final thesis drafts.
  - **Guided Interview Agent**: Dynamically generates targeted domain questions for thin sections and synthesizes user responses into source-tagged academic prose.
- **Plagiarism Detection**: Internal cosine similarity against ingested ChromaDB vector corpora and optional external check integration.
- **Document Assembly**: Direct generation of Microsoft Word (`.docx`) and print-ready vector PDF documents via WeasyPrint and Matplotlib chart generators.
- **Modern Interactive Web UI**: High-fidelity React + Tailwind dashboard with live upload parsing, interactive outline editor, citation manager, and export suite.
- **Containerized Architecture**: Docker & Docker Compose setup with Nginx reverse proxy and FastAPI backend.

---

## 🚀 Quickstart

### Deploy with Docker Compose (Recommended)

1. Clone repository and create `.env`:
   ```bash
   cp .env.example .env
   ```
2. Insert your Groq API key into `.env`:
   ```env
   GROQ_API_KEY=gsk_your_groq_api_key_here
   ```
3. Build and launch containers:
   ```bash
   docker compose up --build -d
   ```
4. Access the application:
   - **Frontend UI**: [http://localhost](http://localhost)
   - **Interactive API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
   - **System Health**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

For full deployment instructions, cloud hosting guides (AWS / GCP / VPS), and troubleshooting, see [DEPLOYMENT.md](file:///e:/ResearchGPT/DEPLOYMENT.md).

---

## 💻 Local Development

### Backend (FastAPI)
```bash
python -m venv venv
venv\Scripts\activate      # On Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```

---

## 📂 Project Structure

```
ResearchGPT/
├── Dockerfile.backend          # FastAPI + WeasyPrint Linux container
├── docker-compose.yml          # Two-tier container orchestration
├── requirements.txt            # Python dependencies (FastAPI, LangGraph, etc.)
├── DEPLOYMENT.md               # Comprehensive production deployment manual
├── app/
│   ├── main.py                 # FastAPI REST API entrypoint & routes
│   ├── agents/                 # LangGraph Multi-Agent pipeline
│   │   ├── graph.py            # StateGraph definition & orchestrator
│   │   ├── structuring.py      # Outline generation agent
│   │   ├── citation.py         # Citation verification agent
│   │   ├── formatting.py       # Template formatting agent
│   │   ├── interview.py        # Guided interview agent
│   │   └── llm.py              # LLM factory (Groq / Ollama)
│   └── services/               # Core business services
│       ├── ingestion/          # PDF/DOCX/TXT chunking & ChromaDB embedder
│       ├── citation.py         # Citeproc-py formatting & CSL styles
│       ├── plagiarism/         # Cosine similarity checker & report generator
│       └── document_assembly/  # Word (.docx) & WeasyPrint (.pdf) builders
├── frontend/
│   ├── Dockerfile              # Multi-stage build (Node -> Nginx Alpine)
│   ├── nginx.conf              # SPA routing & /api reverse proxy
│   ├── package.json            # React, Tailwind, Lucide dependencies
│   ├── vite.config.js          # Vite config with /api proxy
│   └── src/                    # UI Components, Pages, and API services
└── tests/                      # Automated test suite
```

---

## 📄 License

MIT License.
