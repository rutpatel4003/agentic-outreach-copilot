# 🤖 ReachForge - Cold Outreach Copilot

> **AI-Powered Job Application Assistant with Safety Guardrails**
> Automate personalized outreach at scale while maintaining message quality and fact-checking.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)

---

## 🎯 Overview

**ReachForge** is a production-grade AI system that automates the job application outreach process while maintaining high-quality, personalized communication. It combines **multi-agent orchestration**, **web scraping**, **LLM-powered generation**, and **quality guardrails** to generate fact-checked, personalized messages for job opportunities.

### 🔥 Key Highlights

- **Multi-Agent Architecture**: Built with LangGraph for coordinating scraping, personalization, guardrails, and tracking
- **Safety-First Design**: Fact-checking guardrails prevent AI hallucination and ensure citation-backed claims
- **Production-Ready**: Docker deployment, comprehensive testing, input validation, and security features
- **Contact Discovery**: Automatically extracts relevant contacts (recruiters, hiring managers) with relevance scoring
- **Job Matching**: Identifies and scores job listings based on target role similarity
- **CRM Integration**: Full tracking system with follow-up scheduling and response analytics
- **Privacy-Focused**: Runs locally with Ollama (no external API calls, no data sharing)

---

## ✨ Features

### Core Capabilities

| Feature | Description |
|---------|-------------|
| **🔍 Intelligent Web Scraping** | Multi-strategy scraping (subdomains, path patterns, homepage parsing) with JavaScript rendering support for SPA sites |
| **👥 Contact Extraction** | Automatically identifies recruiters, hiring managers, and key people from team/about pages with relevance scoring |
| **💼 Job Discovery** | Extracts and matches job listings to your target role with similarity scoring |
| **✍️ Personalized Messaging** | Generates 3 message variants per company with fact-based citations from scraped content |
| **🛡️ Quality Guardrails** | Multi-layer validation: fact-checking, tone analysis, citation requirements, generic phrase detection |
| **📊 CRM & Analytics** | Track sent messages, responses, follow-ups, and analyze response rates by company/role |
| **💬 Reply Classification** | AI-powered classification of responses (interested/not interested/needs info) with suggested follow-ups |
| **🔄 Workflow Automation** | End-to-end automated pipeline with retry logic and error recovery |

### Additional Features

- **Resume Parsing**: Supports PDF, DOCX, and TXT formats with skill/experience extraction
- **Message Type Support**: LinkedIn connections, LinkedIn messages, and emails with appropriate length limits
- **Tone Customization**: Professional, casual, or enthusiastic tone modes
- **Manual URL Override**: Provide exact URLs when auto-discovery fails
- **Caching**: 7-day cache for scraped content to respect rate limits
- **Export Functionality**: CSV export of outreach history and analytics
- **Configurable Settings**: Centralized config system with environment variable support

---

## 🏗️ Architecture

### System Design

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Frontend                        │
│  (Resume Upload, Job Config, Message Review, CRM Dashboard)  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  LangGraph Workflow Engine                   │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐ │
│  │  Resume  │──▶│ Scraper  │──▶│Personal- │──▶│Guardrails│ │
│  │  Parser  │   │  Agent   │   │ ization  │   │  System  │ │
│  └──────────┘   └──────────┘   │  Agent   │   └─────┬────┘ │
│                      │          └──────────┘         │      │
│                      │                               │      │
│                      ▼                               ▼      │
│            ┌─────────────────┐          ┌──────────────┐   │
│            │Contact Extractor│          │   Approved   │   │
│            │ Job Matcher     │          │   Messages   │   │
│            └─────────────────┘          └──────┬───────┘   │
│                                                 │           │
│                                                 ▼           │
│                     ┌──────────┐   ┌──────────────────┐    │
│                     │ Tracking │◀──│  Follow-up       │    │
│                     │  Agent   │   │  Scheduler       │    │
│                     └────┬─────┘   └──────────────────┘    │
└──────────────────────────┼──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│             SQLite Database (CRM)                            │
│  Companies │ Contacts │ Messages │ Follow-ups │ Campaigns   │
└─────────────────────────────────────────────────────────────┘
```

### Agent System

```python
ScraperAgent
├─ Subdomain discovery (careers.company.com)
├─ Path pattern matching (/careers, /about)
├─ Homepage link extraction
├─ JavaScript rendering (Playwright)
└─ Content extraction (BeautifulSoup)

PersonalizationAgent
├─ Resume parsing & skill extraction
├─ LLM prompt engineering
├─ JSON response parsing
├─ Citation validation (min 2 per message)
└─ Multi-variant generation (3 versions)

GuardrailsSystem
├─ Word count validation (≤200 words)
├─ Citation counting ([source: page])
├─ Generic phrase detection (regex)
├─ Fact-checking (LLM-based)
└─ Tone analysis (LLM-based)

TrackingAgent
├─ Database persistence (SQLAlchemy)
├─ Follow-up scheduling (7-day default)
├─ Status management (sent/replied/no response)
└─ Analytics calculation (response rates)

ReplyAgent
├─ Reply classification (interested/not/needs info)
├─ Sentiment analysis
├─ Follow-up suggestion generation
└─ Action recommendations
```

---

## 🚀 Tech Stack

| Layer | Technologies |
|-------|-------------|
| **LLM Framework** | LangGraph (multi-agent orchestration), Ollama (local inference) |
| **AI Models** | Qwen 3 4B (lightweight, fast), supports Llama 3.1, GPT-4 |
| **Web Scraping** | Playwright (browser automation), BeautifulSoup4 (HTML parsing), JavaScript rendering |
| **Backend** | Python 3.10+, SQLAlchemy (ORM), SQLite (database) |
| **Frontend** | Streamlit (interactive UI/dashboard) |
| **Testing** | pytest, unittest, 80% test coverage target |
| **DevOps** | Docker, docker-compose, GitHub Actions (CI/CD) |
| **Security** | Input validation, SQL injection prevention, rate limiting |

---

## 📦 Installation

### Prerequisites

- Python 3.10 or higher
- [Ollama](https://ollama.ai/) installed locally
- Git

### Option 1: Local Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/cold-outreach-copilot.git
cd cold-outreach-copilot

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Pull the AI model (Qwen 3 4B recommended)
ollama pull qwen3:4b-instruct

# Set up environment variables
cp .env.example .env
# Edit .env with your preferences

# Initialize database
python -c "from src.database.models import init_db; init_db()"

# Run the application
streamlit run app/streamlit_app.py
```

### Option 2: Docker (Recommended - Easy Setup)

**Windows:**
```cmd
docker-setup.bat
```

**Linux/Mac:**
```bash
chmod +x docker-setup.sh
./docker-setup.sh
```

**Manual Docker Setup:**
```bash
# Create environment file
cp .env.example .env

# Build and start containers
docker-compose up -d --build

# Pull AI model (first time only)
docker-compose --profile init up ollama-init

# Access the app at http://localhost:8501
```

📖 **See [DOCKER.md](DOCKER.md) for complete Docker documentation**

---

## 🎮 Usage

### Quick Start

1. **Upload Resume**: Drag & drop your PDF/DOCX resume
2. **Configure Job**: Enter target role and company URL
3. **Generate Messages**: AI creates 3 personalized variants
4. **Review & Approve**: Check citations and quality scores
5. **Track Outreach**: View CRM dashboard with analytics

### Web Interface

```bash
streamlit run app/streamlit_app.py
```

Navigate to `http://localhost:8501` and use the multi-tab interface:

- **Generate Tab**: Create new outreach messages
- **Track Tab**: View sent messages and analytics
- **Replies Tab**: Analyze responses and get follow-up suggestions

### Python API

```python
from src.workflows.outreach_graph import OutreachWorkflow

# Initialize workflow
workflow = OutreachWorkflow(model_name="qwen3:4b-instruct")

# Run end-to-end
result = workflow.run(
    resume_path="path/to/resume.pdf",
    target_role="Software Engineer",
    company_url="https://example.com",
    message_type="linkedin_message",
    tone="professional"
)

# Access results
if result['status'] == 'tracked':
    message = result['selected_variant']['message']
    citations = result['selected_variant']['citations']
    guardrail_score = result['guardrail_result']['overall_score']
```

---

## 🛡️ Guardrails System

### Multi-Layer Quality Checks

```
Message Input
    │
    ├─► 1. Length Validation (≤200 words)
    │
    ├─► 2. Citation Counting (≥2 required)
    │        Format: [source: about], [source: careers]
    │
    ├─► 3. Generic Phrase Detection
    │        Flags: "I am reaching out", "hope this finds you well"
    │
    ├─► 4. Fact-Checking (LLM-powered)
    │        Verifies claims against scraped source material
    │        Detects hallucinations and unverified statements
    │
    └─► 5. Tone Validation (LLM-powered)
            Ensures professional/casual/enthusiastic consistency
            Flags inappropriate language
```

### Scoring System

- **≥90%**: ✅ Approved (message sent)
- **60-89%**: ⚠️ Needs Revision (auto-retry up to 2x)
- **<60%**: ❌ Rejected (workflow fails)

---

## 📊 Database Schema

```sql
-- Core tables for CRM functionality
Company (id, name, url, domain, mission, about_text, careers_text, ...)
Contact (id, company_id, name, title, email, linkedin_url, x_handle, ...)
OutreachMessage (id, company_id, contact_id, message_content, status, ...)
FollowUp (id, original_message_id, scheduled_date, ...)
Campaign (id, name, target_role, resume_hash, stats, ...)

-- Enums
OutreachStatus: draft, sent, replied, no_response, bounced, interested, ...
MessageChannel: linkedin_connection, linkedin_message, email, x
ReplyCategory: interested, not_interested, needs_info, out_of_office
```

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_scraper_agent.py -v

# Run integration tests
pytest tests/test_integration.py -v
```

**Test Coverage**: Core functionality covered with unit and integration tests

---

## 📈 Performance & Scalability

### Expected Performance

The system's performance depends on several factors including site complexity, model size, and hardware specifications:

- **Company scraping**: Varies by website (typically 10-30 seconds for 4 pages with JavaScript rendering)
- **Message generation**: Depends on LLM model (Qwen 3 4B: ~5-10 seconds per variant on CPU)
- **Guardrails validation**: ~2-5 seconds per message for fact-checking
- **Full workflow**: ~30-60 seconds per company end-to-end

### System Requirements

- **Minimum**: 4GB RAM, 2 CPU cores, 10GB disk space
- **Recommended**: 8GB+ RAM, 4+ CPU cores, 20GB disk space
- **GPU**: Optional (improves LLM inference speed significantly)

---

## 🔒 Security & Privacy

### Security Features

✅ **Input Validation**: Email, URL, text length validation to prevent injection attacks
✅ **SQL Injection Prevention**: Parameterized queries with SQLAlchemy ORM
✅ **Rate Limiting**: Respects `robots.txt` and implements request delays
✅ **Sanitization**: Text sanitization removes dangerous characters
✅ **Local Processing**: All data stays on your machine (Ollama runs locally)

### Privacy Considerations

- **No External APIs**: Ollama runs entirely locally
- **No Data Sharing**: Scraped data cached locally only
- **Configurable Storage**: Control where data is stored
- **GDPR-Friendly**: No personally identifiable information sent externally

### Ethical Usage

⚠️ **This tool is designed for ethical job application outreach only**

- ✅ Use for legitimate job applications
- ✅ Respect company preferences (check robots.txt)
- ✅ Follow platform terms of service (LinkedIn, etc.)
- ❌ Do not use for spam or unsolicited marketing
- ❌ Do not exceed rate limits or DDoS sites

---

## 📁 Project Structure

```
cold_outreach_copilot/
├── app/
│   └── streamlit_app.py          # Streamlit web interface (746 lines)
├── src/
│   ├── agents/                   # AI agent implementations
│   │   ├── scraper_agent.py      # Web scraping + contact extraction
│   │   ├── personalization_agent.py  # Message generation
│   │   ├── tracking_agent.py     # CRM operations
│   │   └── reply_agent.py        # Reply classification
│   ├── database/                 # Data layer
│   │   ├── models.py             # SQLAlchemy ORM models
│   │   └── crud.py               # Database operations (557 lines)
│   ├── tools/                    # Utilities
│   │   ├── guardrails.py         # Quality checking system (339 lines)
│   │   ├── llm_interface.py      # Ollama wrapper
│   │   └── web_scraper.py        # Playwright + BeautifulSoup
│   ├── workflows/                # Orchestration
│   │   └── outreach_graph.py     # LangGraph workflow (420 lines)
│   ├── utils/                    # Helpers
│   │   ├── resume_parser.py      # PDF/DOCX parsing
│   │   ├── prompt_templates.py   # LLM prompts
│   │   └── validators.py         # Input validation (NEW!)
│   └── config.py                 # Centralized configuration (NEW!)
├── tests/                        # Unit & integration tests
│   ├── test_agents.py            # Agent tests (274 lines)
│   ├── test_scraper_agent.py     # Scraper tests (NEW!)
│   └── test_validators.py        # Validation tests (NEW!)
├── data/                         # Application data
│   ├── outreach.db               # SQLite database
│   ├── uploads/                  # User resume uploads
│   └── scraped_content/          # Web scraping cache
├── .github/
│   └── workflows/
│       └── ci.yml                # GitHub Actions CI/CD
├── Dockerfile                    # Docker image definition
├── docker-compose.yml            # Multi-container setup
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variable template
├── Makefile                      # Common commands
├── pyproject.toml                # Modern Python configuration
└── README.md                     # This file
```

**Total**: 3,500+ lines of Python code (excluding tests)

---

## 🔧 Configuration

### Environment Variables

```bash
# LLM Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen3:4b-instruct
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000

# Scraper Configuration
SCRAPER_RATE_LIMIT=2.0           # Seconds between requests
SCRAPER_TIMEOUT=30000            # Milliseconds
SCRAPER_CACHE_ENABLED=true
SCRAPER_JS_RENDERING=true        # Enable for modern SPA sites

# Guardrails Configuration
MIN_CITATIONS=2                  # Minimum citations per message
MAX_WORD_COUNT=200              # Maximum message length
MIN_APPROVAL_SCORE=0.9          # Approval threshold (90%)

# Database Configuration
DATABASE_PATH=data/outreach.db

# Follow-up Configuration
AUTO_SCHEDULE_FOLLOWUPS=true
DEFAULT_FOLLOWUP_DAYS=7

# Logging
LOG_LEVEL=INFO
LOG_FILE_PATH=data/app.log
```

---

## 🛠️ Development Commands

### Local Development Workflow

```bash
# Install dependencies
make install

# Run tests
make test

# Lint code
make lint

# Format code
make format

# Build Docker
make docker-build

# Run Docker
make docker-run

# Clean cache files
make clean
```

---

## 🗺️ Roadmap

### ✅ Completed Features

- [x] Multi-agent workflow with LangGraph
- [x] Web scraping with JavaScript rendering
- [x] Contact extraction with relevance scoring
- [x] Job discovery and matching
- [x] Guardrails system with fact-checking
- [x] CRM with follow-up scheduling
- [x] Reply classification
- [x] Streamlit dashboard
- [x] Input validation and security
- [x] Centralized configuration system
- [x] Docker deployment with docker-compose
- [x] Bulk company upload (CSV)
- [x] Company groups management
- [x] Message variant generation (3 per company)
- [x] Export functionality (CSV)

### 📋 Future Enhancements

- [ ] Email auto-send integration (Gmail, SMTP)
- [ ] Chrome extension for LinkedIn
- [ ] Vector search for better resume-job matching
- [ ] A/B testing for message variants
- [ ] Success predictor (ML-based response rate prediction)
- [ ] Job board monitoring automation
- [ ] Fine-tuning support for custom models
- [ ] FastAPI REST API
- [ ] Multi-LLM support (OpenAI, Anthropic, Claude)
- [ ] Enhanced analytics dashboard
- [ ] Database migrations with Alembic
- [ ] CI/CD pipeline with GitHub Actions
- [ ] Webhook integrations (Slack, Discord)
- [ ] User authentication & multi-tenancy

---

## 🐛 Known Issues & Limitations

| Issue | Impact | Workaround |
|-------|--------|------------|
| Some SPA sites don't render | Careers pages may be empty | Use manual URL override |
| LLM may fail JSON parsing | Generation retry needed | Retry logic handles this |
| LinkedIn rate limiting | Frequent scraping blocked | Use caching, respect delays |
| Small models hallucinate | Guardrails may reject | Use larger model or adjust thresholds |
| No email sending | Manual copy-paste needed | Planned for v2.0 |

---

## 🤝 Contributing

Contributions welcome! Please follow these guidelines:

1. **Fork** the repository
2. **Create a feature branch**: `git checkout -b feature/your-feature`
3. **Write tests** for new functionality
4. **Ensure tests pass**: `pytest tests/`
5. **Lint code**: `flake8 src/`
6. **Commit with clear messages**: `git commit -m "Add feature: X"`
7. **Push** and create a **Pull Request**

---

## 📄 License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) file for details.

---

## 👨‍💻 Author

- GitHub: [@rutpatel4003](https://github.com/rutpatel4003)
- LinkedIn: [Rut Patel](https://linkedin.com/in/rutpatel6684)

---

## 🙏 Acknowledgments

- **LangGraph** for multi-agent orchestration
- **Ollama** for local LLM inference
- **Playwright** for JavaScript rendering
- **Streamlit** for rapid UI development

---

## 📚 Additional Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Ollama Models](https://ollama.ai/library)
- [Playwright Python](https://playwright.dev/python/)
- [SQLAlchemy ORM](https://www.sqlalchemy.org/)

---

**⭐ If you find this project useful, please star it on GitHub!**
