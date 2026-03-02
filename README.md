# VoltLegal — Comprehensive Indian Legal Assistant Bot

VoltLegal is a powerful Telegram bot designed to serve as an accessible, comprehensive Indian legal assistant. It uses a hybrid AI architecture powered by **Groq** (LLaMA 3.3 70B) and **Google Gemini** (2.5 Flash) to provide users with accurate legal information, document analysis, and situational guidance.

---

## 🚀 Key Features

*   **Legal Q&A & Info Retrieval:** Ask any legal question in plain language and receive structured, easy-to-understand explanations referencing relevant Indian laws.
*   **Document Analysis (Scan & Explain):** Upload PDF files, Word Documents (`.doc`, `.docx`), or images/photos of legal documents. The bot will read the document, explain its contents, summarize key clauses, highlight red flags, and suggest practical steps using Gemini Vision/Flash.
*   **Voice Message Support:** Send a voice message explaining your situation or asking a question. The bot transcribes the audio using Gemini and answers the legal query.
*   **Interactive Situation Help:** Provide step-by-step details about your legal situation (what happened, who is involved, where, etc.), and the bot will analyze your rights, applicable laws, and suggest options.
*   **Document Drafting:** Draft formal legal documents like Police Complaints (FIR requests), Consumer Complaints, Legal Notices, Workplace Complaints, or RTI Applications through an interactive intake flow.
*   **IPC & BNS Lookup:** Look up specific Indian Penal Code (IPC) or Bharatiya Nyaya Sanhita (BNS) sections to get simple explanations and punishments.
*   **Legal Glossary:** Get definitions for complex legal terms in beginner-friendly language with real-world examples.
*   **Multilingual Support (Translations):** Translate any response into **Hindi** or **Telugu** for better accessibility.

---

## 🛠️ Workflows & Commands

Here is the complete list of bot commands to access its features:

### General & Help
*   `/start` - Start the bot and see the welcome message.
*   `/help` - View the help guide on how to use VoltLegal.
*   `/about` - Learn more about the bot's features and mission.
*   `/rights` - Quick reference guide to fundamental rights in India.
*   `/feedback` - Provide feedback, suggestions, or report issues safely.
*   `/clear` / `/cancel` - Clear the current context, exit an interactive mode, and switch back to general legal queries.

### Legal Queries & Interactive Modes
*   `/scan` - Gives instructions on how to use the Scan & Explain feature (Upload a PDF, Word doc, or photo).
*   `/ipc <section>` - Look up an IPC or BNS section (e.g., `/ipc 420`, `/ipc 302`).
*   `/glossary <term>` - Ask for the simple meaning of a legal term (e.g., `/glossary bail`).
*   `/situation` - Start the interactive Situation Intake process to get a full analysis of your legal standing.
*   `/draft` - Start the interactive Document Drafting process to generate formal complaints or notices.

### Translation
*   `/hindi` - Translate the bot's last response into Hindi.
*   `/telugu` - Translate the bot's last response into Telugu.

---

## ⚙️ Architecture & Technologies

*   **Telegram Bot API:** (`python-telegram-bot` wrapper)
*   **LLMs:**
    *   **Groq API (Llama 3.3 70B Versatile):** Handles heavy text processing including Legal Q&A, Situation Analysis, IPC Lookup, Glossary, Drafting, and Translations (Hindi/Telugu). Chosen for fast, robust inference capabilities.
    *   **Google Gemini API (Gemini 2.5 Flash):** Handles multimodal input processing such as reading PDFs (`pymupdf`), Word Documents (`python-docx`), Images (`Pillow`), and Voice Message transcription.
*   **Rate Limiting:** Protects the bot from abusive usage (Max requests limited per minute per user).
*   **Local Database:** `voltlegal.db` (SQLite structure).

---

## 💻 Setup & Installation

### Prerequisites
*   Python 3.9+
*   Telegram Bot Token (Get from [BotFather](https://t.me/botfather))
*   Groq API Key
*   Google Gemini API Key

### Steps

1.  **Clone the project** to your local machine.
2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Create a `.env` file** in the project root and add your API keys:
    ```env
    TELEGRAM_BOT_TOKEN=your_telegram_token_here
    GROQ_API_KEY=your_groq_key_here
    GEMINI_API_KEY=your_gemini_key_here
    ```
4.  **Run the application:**
    ```bash
    python main.py
    ```

---

*Note: VoltLegal is an AI assistant providing legal **information**, not professional legal **advice**. Always consult a qualified lawyer for serious legal issues.*
