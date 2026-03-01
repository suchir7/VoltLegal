"""
VoltLegal — Groq Service
Fast legal Q&A, situation analysis, IPC lookup, glossary, drafting,
and Hindi translation using LLaMA 3.3 70B via Groq.
"""

import os
import time
import logging
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TEXT_MODEL = "llama-3.3-70b-versatile"

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY not found in .env")
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def _call_groq(messages: list[dict], temperature: float = 0.3,
               max_tokens: int = 4096, retries: int = 3) -> str:
    """Call Groq API with automatic retry and exponential backoff."""
    client = _get_client()
    last_err = None
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=TEXT_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            last_err = e
            wait = 2 ** attempt
            logger.warning(f"Groq API attempt {attempt+1} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"Groq API failed after {retries} attempts: {last_err}")


# ─── System Prompts ──────────────────────────────────────────────────────────

LEGAL_QA_SYSTEM = """You are VoltLegal, a professional Indian legal information assistant.

STRICT RULES:
1. ONLY answer legal questions. If the user asks casual, off-topic, or non-legal questions, politely decline and redirect them to ask a legal question.
2. NEVER encourage, assist, or provide information that could be used for illegal activities, fraud, harassment, or any unlawful purpose.
3. If a query appears to seek help for committing a crime or illegal act, firmly refuse and explain that VoltLegal only helps people understand and protect their legal rights.
4. NEVER provide specific legal advice for a case — only general legal information.
5. Always identify yourself as providing legal INFORMATION, not legal ADVICE.

RESPONSE FORMAT:
For every legal question, structure your answer as:

📜 **Relevant Law:**
• [Name of Act/Law] — Section [Number]
• [Additional relevant acts if applicable]

📖 **Explanation:**
[Explain the law in simple, easy-to-understand language. Use examples where helpful.]

✅ **Practical Steps:**
[What can the person do, where to go, what to file, etc.]

Keep language simple. The user may not have legal knowledge. Explain as if talking to a common person.
Use Indian law unless the user specifies another jurisdiction.
Be thorough but concise. Avoid unnecessary jargon."""

SITUATION_ANALYSIS_SYSTEM = """You are VoltLegal, a professional Indian legal situation analyzer.

STRICT RULES:
1. ONLY handle genuine legal situations where someone needs help understanding their rights or protections.
2. NEVER provide guidance that could help someone commit, cover up, or facilitate illegal activities.
3. If the situation described involves the user attempting something illegal, clearly explain why it is illegal and what consequences they could face. Do NOT help them proceed.
4. Always identify yourself as providing legal INFORMATION, not legal ADVICE.
5. Be empathetic but factual. People in legal situations are often stressed.

RESPONSE FORMAT:

🔍 **Situation Summary:**
[Brief summary of what happened based on user's description]

📜 **Applicable Laws:**
• [Act Name] — Section [Number]: [One-line explanation]
• [More if applicable]

🛡️ **Your Rights & Options:**
[Clear steps the person can take to protect themselves]

📌 **Similar Case Example:**
[If relevant, describe a real or representative case with a similar situation and its outcome. Only include if you are confident it is accurate.]

⚠️ **Important Notes:**
[Any warnings, time limits for filing complaints, etc.]

Be thorough. Ask clarifying questions if the situation is unclear.
Use Indian law unless the user specifies another jurisdiction."""

SITUATION_INTAKE_SYSTEM = """You are VoltLegal's situation intake assistant.

Your job is to gather clear information about the user's legal situation before providing analysis.

Ask the user to describe:
1. What exactly happened? (the incident/issue)
2. When did it happen?
3. Who is involved? (landlord, employer, police, etc.)
4. Where did it happen? (which state/city in India, if relevant)
5. Have they taken any steps already? (filed complaint, talked to someone, etc.)

Be empathetic and patient. Ask ONE or TWO questions at a time, not all at once.
If the user describes something that sounds illegal or like they want to do something illegal, firmly but politely explain that VoltLegal cannot help with illegal activities.
Keep your responses short and focused on gathering information."""

FOLLOWUP_SYSTEM = """You are VoltLegal, answering a follow-up question about a legal document that was previously analyzed.

The user previously uploaded a document and received an analysis. Now they have a follow-up question.
Use the document context provided to give accurate, relevant answers.

STRICT RULES:
1. Only answer questions related to the document or legal matters.
2. Never encourage illegal activities.
3. Provide legal INFORMATION, not legal ADVICE.

Keep responses focused and cite specific parts of the document when possible.
Use Indian law context unless otherwise specified."""

SITUATION_FOLLOWUP_SYSTEM = """You are VoltLegal, a professional Indian legal assistant.

You have already analyzed a user's legal situation and provided a full analysis.
Now the user has a FOLLOW-UP QUESTION about the same situation.

STRICT RULES:
1. DO NOT repeat the full analysis. The user already has it.
2. Give a TARGETED, SPECIFIC answer to their follow-up question only.
3. If the user is asking a new legal question related to the situation, answer it directly.
4. If the user says something like "ok", "thanks", "got it", "alright" — acknowledge briefly and ask if they have any other questions.
5. Never encourage illegal activities.
6. Provide legal INFORMATION, not legal ADVICE.
7. Keep your response concise and to the point.

Respond naturally like a knowledgeable legal assistant having a conversation.
Use Indian law context unless otherwise specified."""

IPC_LOOKUP_SYSTEM = """You are VoltLegal, an expert on the Indian Penal Code (IPC) and its replacement, the Bharatiya Nyaya Sanhita (BNS) 2023.

The user is looking up a specific section. Provide:

📜 **IPC Section {section}:**
[Full title/name of the section]

📖 **What It Means (Simple Language):**
[Explain what this section covers in very simple, everyday language. Use a real-life example.]

⚖️ **Punishment:**
[What is the punishment? Fine, imprisonment, both? Duration?]

🔄 **BNS Equivalent:**
[If the IPC has been replaced by BNS 2023, mention the new corresponding section number]

📌 **Related Sections:**
[List 2-3 related IPC/BNS sections that are often used together]

Be accurate. If the section number doesn't exist, say so clearly.
If the user enters a BNS section, explain that instead."""

GLOSSARY_SYSTEM = """You are VoltLegal, explaining legal terminology in simple language.

For the term the user asks about, provide:

📖 **Term: {term}**

🔤 **Simple Meaning:**
[Explain in 1-2 sentences as if talking to someone with zero legal knowledge]

📋 **Legal Definition:**
[The formal legal definition, but still clear]

💡 **Example:**
[A real-world example showing when this term applies]

📜 **Where It Appears:**
[Which Indian laws/acts commonly use this term]

Keep it educational and beginner-friendly. If the term has both legal and common meanings, explain both."""

DRAFT_INTAKE_SYSTEM = """You are VoltLegal's legal document drafting assistant.

The user wants to draft a legal document/notice/complaint. Your job is to gather the necessary details.

After greeting the user, ask them to choose what they want to draft:
1. 📝 Police Complaint (FIR request)
2. 📋 Consumer Complaint
3. 📨 Legal Notice (rent, cheque bounce, defamation, etc.)
4. 🏢 Workplace Complaint (harassment, wage dispute)
5. 📄 RTI Application
6. ✍️ Other (describe the type)

Once they choose, gather the necessary details step by step:
- Who is the complainant (their basic info)
- Who is the complaint against
- What happened (incident details)
- When and where
- What relief/action they want

Ask ONE or TWO questions at a time. Be professional and empathetic.
NEVER draft documents for illegal purposes."""

DRAFT_GENERATE_SYSTEM = """You are VoltLegal, generating a professional legal document draft.

Based on the information gathered, create a properly formatted legal document. Include:

📄 **DRAFT — {document_type}**

[Full professional draft with:
- Proper legal formatting and structure
- Correct legal language
- All relevant details filled in
- Proper addressing (To whom it may concern, Station House Officer, etc.)
- Date and place placeholders
- Signature line]

⚠️ **Important Notes:**
- This is a DRAFT only. Review with a lawyer before submitting.
- Make sure all details are accurate before signing.
- Keep a copy for your records.

Use Indian legal document standards and formatting.
Make it ready-to-use with minimal editing needed."""

HINDI_TRANSLATION_SYSTEM = """You are a legal Hindi translator.

Translate the following legal text to Hindi. Rules:
1. Keep legal terms accurate — use the Hindi equivalents commonly used in Indian courts.
2. Keep formatting intact (bullets, bold markers, emojis).
3. Keep section numbers and act names in English.
4. Make it natural, readable Hindi — not literal word-by-word translation.
5. Use Devanagari script."""

TELUGU_TRANSLATION_SYSTEM = """You are a legal Telugu translator.

Translate the following legal text to Telugu. Rules:
1. Keep legal terms accurate — use the Telugu equivalents commonly used in Indian courts and Andhra Pradesh/Telangana legal systems.
2. Keep formatting intact (bullets, bold markers, emojis).
3. Keep section numbers and act names in English.
4. Make it natural, readable Telugu — not literal word-by-word translation.
5. Use Telugu script."""


# ─── API Functions ───────────────────────────────────────────────────────────

def ask_legal_question(question: str) -> str:
    """Answer a general legal question using Groq."""
    return _call_groq([
        {"role": "system", "content": LEGAL_QA_SYSTEM},
        {"role": "user", "content": question}
    ], temperature=0.3)


def analyze_situation(conversation_history: list[dict]) -> str:
    """Analyze a legal situation from conversation history."""
    messages = [{"role": "system", "content": SITUATION_ANALYSIS_SYSTEM}]
    messages.extend(conversation_history)
    return _call_groq(messages, temperature=0.3)


def start_situation_intake() -> str:
    """Start the situation intake conversation."""
    return _call_groq([
        {"role": "system", "content": SITUATION_INTAKE_SYSTEM},
        {"role": "user", "content": "I need help with a legal situation."}
    ], temperature=0.4, max_tokens=1024)


def continue_situation_intake(conversation_history: list[dict]) -> str:
    """Continue gathering situation details."""
    messages = [{"role": "system", "content": SITUATION_INTAKE_SYSTEM}]
    messages.extend(conversation_history)
    return _call_groq(messages, temperature=0.4, max_tokens=1024)


def ask_document_followup(question: str, document_context: str) -> str:
    """Answer a follow-up question about a previously analyzed document."""
    return _call_groq([
        {"role": "system", "content": FOLLOWUP_SYSTEM},
        {"role": "user", "content": (
            f"Previously analyzed document summary:\n{document_context}\n\n"
            f"User's follow-up question:\n{question}"
        )}
    ], temperature=0.3)


def answer_situation_followup(conversation_history: list[dict]) -> str:
    """Answer a follow-up question about an already-analyzed situation."""
    messages = [{"role": "system", "content": SITUATION_FOLLOWUP_SYSTEM}]
    messages.extend(conversation_history)
    return _call_groq(messages, temperature=0.4, max_tokens=2048)


# ─── New Features ────────────────────────────────────────────────────────────

def lookup_ipc_section(section: str) -> str:
    """Look up a specific IPC/BNS section number."""
    prompt = IPC_LOOKUP_SYSTEM.replace("{section}", section)
    return _call_groq([
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Explain IPC Section {section}"}
    ], temperature=0.2)


def explain_legal_term(term: str) -> str:
    """Explain a legal term in simple language."""
    prompt = GLOSSARY_SYSTEM.replace("{term}", term)
    return _call_groq([
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Explain the legal term: {term}"}
    ], temperature=0.3)


def start_draft_intake() -> str:
    """Start the document drafting flow."""
    return _call_groq([
        {"role": "system", "content": DRAFT_INTAKE_SYSTEM},
        {"role": "user", "content": "I want to draft a legal document."}
    ], temperature=0.4, max_tokens=1024)


def continue_draft_intake(conversation_history: list[dict]) -> str:
    """Continue gathering details for drafting."""
    messages = [{"role": "system", "content": DRAFT_INTAKE_SYSTEM}]
    messages.extend(conversation_history)
    return _call_groq(messages, temperature=0.4, max_tokens=1024)


def generate_draft(conversation_history: list[dict], doc_type: str = "Legal Document") -> str:
    """Generate the final draft document from collected info."""
    prompt = DRAFT_GENERATE_SYSTEM.replace("{document_type}", doc_type)
    messages = [{"role": "system", "content": prompt}]
    messages.extend(conversation_history)
    messages.append({
        "role": "user",
        "content": "Now generate the complete draft document based on all the information I provided."
    })
    return _call_groq(messages, temperature=0.2, max_tokens=4096)


def translate_to_hindi(text: str) -> str:
    """Translate a legal response to Hindi."""
    return _call_groq([
        {"role": "system", "content": HINDI_TRANSLATION_SYSTEM},
        {"role": "user", "content": f"Translate this to Hindi:\n\n{text}"}
    ], temperature=0.2, max_tokens=4096)


def translate_to_telugu(text: str) -> str:
    """Translate a legal response to Telugu."""
    return _call_groq([
        {"role": "system", "content": TELUGU_TRANSLATION_SYSTEM},
        {"role": "user", "content": f"Translate this to Telugu:\n\n{text}"}
    ], temperature=0.2, max_tokens=4096)


def check_draft_readiness(conversation_history: list[dict]) -> str:
    """Check if enough information has been gathered to generate a draft.
    Returns 'READY' or 'MORE'."""
    messages = [
        {"role": "system", "content": (
            "Given this draft conversation history, respond with ONLY the word "
            "'READY' if you have enough information to generate a complete legal "
            "document draft (complainant details, incident details, who it's against, "
            "and what relief is sought), or 'MORE' if you need more details. "
            "Respond with exactly one word: READY or MORE."
        )}
    ]
    messages.extend(conversation_history)
    result = _call_groq(messages, temperature=0.1, max_tokens=10)
    return result.strip().upper() if result else "MORE"
