title: VoltLegal Bot
emoji: ⚖️
colorFrom: blue
colorTo: green
sdk: docker
pinned: false

# ⚖️ VoltLegal — AI-Powered Indian Legal Assistant

**VoltLegal** is a Telegram bot that helps everyday people understand Indian law in simple language. It combines **Groq (LLaMA 3.3 70B)** for fast legal reasoning with **Google Gemini 2.5 Flash** for document/image/voice processing — all through an intuitive chat interface.

> ⚠️ VoltLegal provides legal **information** only, not legal advice. Always consult a qualified lawyer for your specific situation.

---

## ✨ Features

### 📄 Document Scan & Explain
Send any legal document and VoltLegal reads, analyzes, and explains it in plain language.
- **PDF files** — Parsed and analyzed via Gemini
- **Photos / Screenshots** — Gemini Vision reads text from images
- **Word documents** (.doc, .docx) — Extracted and analyzed
- **Follow-up questions** — Ask questions about the analyzed document

### 🛡️ Situation Help (`/situation`)
Describe a legal situation step-by-step. VoltLegal gathers details through a guided conversation, then provides:
- Applicable laws and sections
- Your rights and options
- Similar case examples
- Important warnings and deadlines

### 📚 Legal Q&A
Type any legal question directly — VoltLegal answers with relevant Acts, sections, explanations, and practical steps.

### ✍️ Document Drafting (`/draft`)
Draft legal documents through a guided flow:
- 📝 Police complaints (FIR requests)
- 📋 Consumer complaints
- 📨 Legal notices (rent, cheque bounce, defamation)
- 🏢 Workplace complaints
- 📄 RTI applications

**Smart trigger** — The bot uses AI to detect when enough information is gathered, or respond to keywords like `generate`, `draft it`, `ready`, `done`, `banao`.

### 📕 IPC/BNS Lookup (`/ipc <section>`)
Look up any IPC section with:
- Plain-language explanation
- Punishment details
- BNS 2023 equivalent
- Related sections

### 📖 Legal Glossary (`/glossary <term>`)
Explain any legal term (bail, FIR, habeas corpus, etc.) in simple language with real-world examples.

### 🎤 Voice Messages
Send a voice note — Gemini transcribes it, then Groq answers the legal question. Supports Hindi, Telugu, and other Indian languages.

### 🌐 Translation
- `/hindi` — Translate any response to Hindi
- `/telugu` — Translate any response to Telugu
- Or just type `hindi`, `తెలుగు`, `telugu lo cheppu` as a message

### 🇮🇳 Know Your Rights (`/rights`)
Quick reference card covering:
- Police encounter rights
- Tenant rights
- Workplace rights
- Consumer rights
- RTI information
- Medical rights

### 📋 Activity History (`/history`)
View your last 10 interactions with type icons and timestamps.

### 💬 Feedback (`/feedback`)
Submit feedback directly through the bot — stored in the database for review.

---

## 🏗️ Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Telegram    │────▶│   main.py    │────▶│  groq_service│
│    User       │◀────│  (handlers)  │     │  (LLaMA 3.3) │
└──────────────┘     └──────┬───────┘     └──────────────┘
                           │
                     ┌─────┴──────┐     ┌──────────────┐
                     │  formatter │     │gemini_service│
                     │  (output)  │     │(Docs/Vision) │
                     └────────────┘     └──────────────┘
                           │
                     ┌─────┴──────┐
                     │   db.py    │
                     │(Turso/SQLite)│
                     └────────────┘
```

| File | Role |
|------|------|
| `main.py` | Telegram handlers, conversation flows, rate limiting |
| `groq_service.py` | Legal Q&A, situation analysis, IPC lookup, glossary, drafting, translation via Groq |
| `gemini_service.py` | PDF/image/Word analysis, voice transcription via Gemini |
| `formatter.py` | Telegram message formatting, disclaimers, quick actions |
| `db.py` | Async database layer — Turso (libSQL) cloud or SQLite fallback |

---

## 🚀 Setup

### Prerequisites
- Python 3.10+
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- A Groq API Key (free at [console.groq.com](https://console.groq.com))
- A Google Gemini API Key (from [Google AI Studio](https://aistudio.google.com))
- *(Optional)* A Turso database for cloud persistence

### Installation

```bash
# Clone the project
git clone <your-repo-url>
cd voltlegal

# Create virtual environment
python -m venv venv
source venv/bin/activate    # Linux/Mac
venv\Scripts\activate       # Windows

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Copy the example env file and fill in your keys:

```bash
cp .env.example .env
```

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key
DB_PATH=voltlegal.db                    # only needed for local/SQLite fallback

# Optional — for Turso cloud database
TURSO_DATABASE_URL=libsql://your-db.turso.io
TURSO_AUTH_TOKEN=your_turso_token
```

### Run

```bash
python main.py
```

The bot will print:
```
⚖️  VoltLegal is starting...
✅ VoltLegal is running! Send messages on Telegram.
```

---

## 📋 All Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome & feature overview |
| `/help` | Full command list |
| `/situation` | Guided legal situation analysis |
| `/draft` | Draft a legal document |
| `/ipc <section>` | Look up an IPC/BNS section |
| `/glossary <term>` | Explain a legal term |
| `/rights` | Know your rights quick card |
| `/scan` | Prompt to upload a document |
| `/hindi` | Translate last response to Hindi |
| `/telugu` | Translate last response to Telugu |
| `/history` | View your recent activity |
| `/about` | About VoltLegal |
| `/feedback` | Share your feedback |
| `/clear` | Clear document context |
| `/cancel` | Cancel current conversation |

---

## 🗄️ Database

VoltLegal uses a dual-backend database system:

- **Turso (libSQL)** — Cloud database when `TURSO_DATABASE_URL` is set
- **SQLite** — Local file fallback when Turso vars are not set

No code changes needed between local development and cloud deployment.

### Tables

| Table | Purpose |
|-------|---------|
| `users` | Telegram user profiles, join dates, query counts |
| `conversations` | Every message pair (user question + bot response) |
| `sessions` | Saved situation/draft conversation histories for resume |
| `feedback` | User feedback messages |

---

## 🔧 Infrastructure

| Feature | Details |
|---------|---------|
| ⌨️ Typing indicators | Bot shows "typing..." while processing |
| 🔄 Retry logic | Groq and Gemini have 3-attempt exponential backoff |
| 🛡️ Rate limiting | Max 8 requests/user/minute |
| 📨 Forwarded messages | Auto-analyzed for legal content |
| 🔄 Auto-clear | Document context expires after 2 hours |
| 💾 Session resume | `/situation` and `/draft` offer to resume previous sessions |
| 🤖 Smart draft trigger | AI detects when enough info is gathered |

---

## ☁️ Deployment

### Render (Current Deployment)
- Deployed as a **Background Worker** on Render
- Auto-deploys on every GitHub push
- Environment variables set in Render dashboard

### Oracle Cloud / Linux (Self-hosted)
A systemd service file is included for self-hosted deployment:

```bash
# Copy service file
sudo cp voltlegal.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable voltlegal
sudo systemctl start voltlegal

# Check status
sudo systemctl status voltlegal

# View logs
journalctl -u voltlegal -f
```

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `python-telegram-bot` | Telegram Bot API |
| `google-generativeai` | Google Gemini (docs, images, voice) |
| `groq` | Groq API (LLaMA 3.3 70B) |
| `python-dotenv` | Environment variable loading |
| `python-docx` | Word document parsing |
| `Pillow` | Image processing |
| `pymupdf` | PDF text extraction |
| `libsql-client` | Turso (libSQL) database client |

---

## 📜 License

This project is for educational and informational purposes. VoltLegal does not provide legal advice and cannot represent users in court.

---

Made with ❤️ for the people of India.
