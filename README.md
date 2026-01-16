# 🤖 Cold Outreach Copilot

> AI-powered job search automation with built-in safety guardrails

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An intelligent agent system that automates cold outreach for job applications by scraping company data, generating personalized messages, validating quality through guardrails, and tracking responses in a CRM.

## ✨ Features

- **🔍 Intelligent Company Research**: Scrapes About, Careers, News, and Team pages
- **✍️ Personalized Message Generation**: Creates 3 variants per company with fact-based citations
- **🛡️ Built-in Guardrails**: Fact-checking, tone validation, and hallucination prevention
- **📊 CRM Tracking System**: Follow-ups, reply detection, and analytics
- **💬 Reply Analysis**: Classifies responses and suggests follow-up messages
- **🧠 Local LLM**: Runs on Ollama (no API costs, works offline)
- **🎨 Interactive UI**: Streamlit dashboard for full workflow management

## 🏗️ Architecture
```
┌─────────────┐
│   Resume    │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│          LangGraph Workflow                 │
│  ┌──────────┐    ┌──────────┐    ┌───────┐ │
│  │ Scraper  │───▶│Personaliz│───▶│Guard- │ │
│  │  Agent   │    │er Agent  │    │rails  │ │
│  └──────────┘    └──────────┘    └───┬───┘ │
│                                      │     │
│                                      ▼     │
│  ┌──────────┐    ┌──────────┐    ┌───────┐ │
│  │ Reply    │◀───│ Tracking │◀───│Approve│ │
│  │ Agent    │    │  Agent   │    │       │ │
│  └──────────┘    └──────────┘    └───────┘ │
└─────────────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│   SQLite    │
│   CRM DB    │
└─────────────┘
```

## 🚀 Tech Stack

| Component | Technology |
|-----------|-----------|
| **Orchestration** | LangGraph |
| **LLM** | Ollama (Llama 3.1 8B) |
| **Scraping** | Playwright + BeautifulSoup + Trafilatura |
| **Database** | SQLite + SQLAlchemy ORM |
| **Frontend** | Streamlit |
| **Language** | Python 3.10+ |

## 📋 Prerequisites

- **Python 3.10+**
- **Ollama** ([Install](https://ollama.ai))
- **RTX 3060 6GB VRAM** (or similar for local LLM)
- **8GB+ RAM**

## 🔧 Installation

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/cold-outreach-copilot.git
cd cold-outreach-copilot
```

### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Install Ollama & Pull Model
```bash
# Install Ollama from https://ollama.ai
curl -fsSL https://ollama.com/install.sh | sh

# Pull Llama 3.1 8B (fits 6GB VRAM)
ollama pull llama3.1:8b

# Start Ollama server
ollama serve
```

### 5. Initialize Database
```bash
python -m src.database.models
```

### 6. Create Data Directories
```bash
mkdir -p data/uploads data/scraped_content data/outputs
```

## 🎮 Usage

### Option 1: Streamlit UI (Recommended)
```bash
streamlit run app/streamlit_app.py
```

**Workflow:**
1. Upload resume (PDF/DOCX/TXT)
2. Configure job settings (role, tone, message type)
3. Enter company URLs (one per line)
4. Click "Generate Messages"
5. Review guardrails report
6. Track in CRM dashboard
7. Analyze replies and get suggestions

### Option 2: Command Line

#### Test Individual Components
```bash
# Test Resume Parser
python -m src.utils.resume_parser resume.pdf

# Test Web Scraper
python -m src.agents.scraper_agent https://company.com

# Test LLM Interface
python -m src.tools.llm_interface

# Test Personalization Agent
python -m src.agents.personalization_agent resume.pdf "Software Engineer"

# Test Guardrails
python -m src.tools.guardrails

# Test Tracking Agent
python -m src.agents.tracking_agent

# Test Reply Agent
python -m src.agents.reply_agent
```

#### Run Full Workflow
```bash
python -m src.workflows.outreach_graph resume.pdf "Software Engineer" https://company.com
```

### Option 3: Python API
```python
from src.workflows.outreach_graph import run_outreach_workflow

result = run_outreach_workflow(
    resume_path="resume.pdf",
    target_role="Software Engineer",
    company_url="https://company.com",
    message_type="linkedin_message",
    tone="professional",
    skip_guardrails=False
)

print(f"Status: {result['status']}")
print(f"Message: {result['selected_variant']['message']}")
```

## 📊 Project Structure
```
cold-outreach-copilot/
├── src/
│   ├── agents/                    # Core AI agents
│   │   ├── scraper_agent.py       # Company data scraping
│   │   ├── personalization_agent.py # Message generation
│   │   ├── tracking_agent.py      # CRM management
│   │   └── reply_agent.py         # Reply classification
│   ├── tools/                     # Utilities
│   │   ├── web_scraper.py         # Playwright wrapper
│   │   ├── llm_interface.py       # Ollama client
│   │   └── guardrails.py          # Fact-checking + tone
│   ├── database/                  # Data layer
│   │   ├── models.py              # SQLAlchemy models
│   │   └── crud.py                # Database operations
│   ├── workflows/                 # Orchestration
│   │   └── outreach_graph.py      # LangGraph workflow
│   └── utils/                     # Helpers
│       ├── resume_parser.py       # PDF/DOCX parsing
│       └── prompt_templates.py    # LLM prompts
├── app/
│   └── streamlit_app.py           # Web UI
├── data/
│   ├── sample_companies.csv       # Test dataset
│   ├── outreach.db                # SQLite database
│   ├── uploads/                   # User resumes
│   └── scraped_content/           # Page cache
├── requirements.txt
├── .env.example
└── README.md
```

## 🛡️ Guardrails System

The guardrails ensure message quality through:

1. **Citation Verification**: All claims must be sourced from scraped data
2. **Tone Validation**: Matches requested tone (professional/casual/enthusiastic)
3. **Word Count Limits**: 100-250 words depending on channel
4. **Generic Phrase Detection**: Flags overused templates
5. **LLM Fact-Checking**: Cross-references claims against source material

**Scoring:**
- ✅ **Approved**: ≥90% checks passed
- ⚠️ **Needs Revision**: 60-89% (auto-retry up to 2x)
- ❌ **Rejected**: <60%

## 📈 Metrics & Analytics

Track your outreach performance:

- **Reply Rate**: % of messages that receive responses
- **Average Response Time**: Hours from send to reply
- **Status Breakdown**: Sent, Replied, No Response, Rejected
- **Follow-up Pipeline**: Pending actions organized by date

## 🧪 Testing
```bash
# Run all tests
python -m tests.test_agents

# Run specific test class
python -m unittest tests.test_agents.TestResumeParser

# With coverage
pip install coverage
coverage run -m unittest tests.test_agents
coverage report
```

## 🔐 Safety & Ethics

- **Rate Limiting**: 2-3 requests/sec to avoid overloading servers
- **robots.txt Compliance**: Respects site crawling policies
- **Caching**: Reduces redundant scraping
- **No Spam**: Encourages genuine, personalized outreach
- **Privacy**: All data stored locally, no third-party APIs

## 🚧 Limitations

- LinkedIn scraping may violate ToS (use public company pages only)
- Requires Ollama server running (CPU/GPU inference)
- English language only (for now)
- Best for tech roles (skill extraction optimized for engineering)

## 🎯 Roadmap

- [ ] Multi-language support
- [ ] A/B testing framework (track which variants perform best)
- [ ] Email integration (auto-send via SMTP)
- [ ] Chrome extension for one-click LinkedIn outreach
- [ ] Fine-tuned LLM on successful outreach examples
- [ ] Sentiment analysis on replies
- [ ] Integration with applicant tracking systems (ATS)

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details

## 🙏 Acknowledgments

- **Anthropic**: For LangGraph framework
- **Ollama**: For local LLM inference
- **Streamlit**: For rapid UI development

## 📧 Contact

**Rut Patel** - USC Master's Student  
GitHub: [@yourusername](https://github.com/rutpatel4003)  
LinkedIn: [your-profile](https://www.linkedin.com/in/rutpatel6684/)

---

**⭐ If this project helped your job search, please star the repo!**
```

---

## 📘 How The Project Works & How To Run It

### **System Architecture**

The project is a **multi-agent AI system** orchestrated by **LangGraph** that automates cold outreach:
```
User → Streamlit UI → LangGraph Workflow → [Scraper → Personalizer → Guardrails → Tracker] → SQLite DB