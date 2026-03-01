"""
VoltLegal — Main Telegram Bot
Comprehensive Indian legal assistant with hybrid AI architecture.
Groq (Legal Q&A, Situation, Draft, IPC, Glossary) + Gemini (Documents, Images, Voice)
"""

import os
import json
import time
import asyncio
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction

import groq_service
import gemini_service
import formatter
import db
from keep_alive import keep_alive

load_dotenv()

# ─── Config ──────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Conversation states
SITUATION_GATHERING = 0
SITUATION_FOLLOWUP = 1
DRAFT_GATHERING = 2
DRAFT_READY = 3
FEEDBACK_WAITING = 4

# Rate limiting: max requests per user per minute
RATE_LIMIT = 8
_user_timestamps: dict[int, list[float]] = defaultdict(list)

# Keywords that immediately trigger draft generation
DRAFT_TRIGGER_KEYWORDS = {
    "generate", "draft it", "create now", "ready", "done",
    "bas karo", "banao", "generate it", "create draft", "draft now",
}

# Auto-clear stale context after this many hours
CONTEXT_EXPIRY_HOURS = 2


# ─── Rate Limiting ───────────────────────────────────────────────────────────

def _check_rate_limit(user_id: int) -> bool:
    """Check if user has exceeded rate limit. Returns True if allowed."""
    now = time.time()
    timestamps = _user_timestamps[user_id]
    # Remove timestamps older than 60 seconds
    _user_timestamps[user_id] = [t for t in timestamps if now - t < 60]
    if len(_user_timestamps[user_id]) >= RATE_LIMIT:
        return False
    _user_timestamps[user_id].append(now)
    return True


# ─── DB Helpers ──────────────────────────────────────────────────────────────

async def _track_user(update: Update):
    """Upsert user and increment query count. Called from every handler."""
    try:
        user = update.effective_user
        if user:
            await db.upsert_user(user.id, user.first_name, user.last_name, user.username)
            await db.increment_query_count(user.id)
    except Exception as e:
        logger.error(f"DB track_user error: {e}")


async def _log_conv(update: Update, conv_type: str, user_msg: str, bot_response: str):
    """Log a conversation pair to the DB."""
    try:
        user = update.effective_user
        if user:
            await db.log_conversation(user.id, conv_type, user_msg, bot_response)
    except Exception as e:
        logger.error(f"DB log_conv error: {e}")


# ─── Utility ─────────────────────────────────────────────────────────────────

async def send_long_message(update: Update, text: str, parse_mode: str = "Markdown"):
    """Split and send messages that exceed Telegram's 4096-char limit."""
    MAX_LEN = 4000
    if len(text) <= MAX_LEN:
        try:
            await update.message.reply_text(text, parse_mode=parse_mode)
        except Exception:
            await update.message.reply_text(text)
        return

    # Split by double newline for natural breaks
    chunks = []
    current = ""
    for paragraph in text.split("\n\n"):
        if len(current) + len(paragraph) + 2 > MAX_LEN:
            if current:
                chunks.append(current)
            current = paragraph
        else:
            current = current + "\n\n" + paragraph if current else paragraph
    if current:
        chunks.append(current)

    for chunk in chunks:
        try:
            await update.message.reply_text(chunk.strip(), parse_mode=parse_mode)
        except Exception:
            await update.message.reply_text(chunk.strip())


async def send_typing(update: Update):
    """Send typing indicator to show the bot is working."""
    try:
        await update.message.chat.send_action(ChatAction.TYPING)
    except Exception:
        pass


# ─── Commands ────────────────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        formatter.build_welcome_message(),
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await update.message.reply_text(
        formatter.build_help_message(),
        parse_mode="Markdown",
    )


async def rights_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /rights command — quick reference to fundamental rights."""
    await update.message.reply_text(
        formatter.build_rights_message(),
        parse_mode="Markdown",
    )


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /scan command — prompt user to upload a document."""
    await update.message.reply_text(
        "📄 *Scan & Explain a Legal Document*\n\n"
        "Send me any legal document and I'll read, analyze, "
        "and explain it in simple language.\n\n"
        "*Supported formats:*\n"
        "📎 PDF file\n"
        "📷 Photo / Screenshot\n"
        "📝 Word document (.doc, .docx)\n\n"
        "👇 _Just send the file or photo now!_",
        parse_mode="Markdown",
    )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about command."""
    await update.message.reply_text(
        formatter.build_about_message(),
        parse_mode="Markdown",
    )


async def ipc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ipc <section> command — look up IPC/BNS sections."""
    if not _check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⏳ You're sending too many requests. Please wait a moment.")
        return

    # Extract section number from command arguments
    args = context.args
    if not args:
        await update.message.reply_text(
            "📕 *IPC/BNS Section Lookup*\n\n"
            "Usage: `/ipc <section number>`\n\n"
            "Examples:\n"
            "• `/ipc 420` — Cheating\n"
            "• `/ipc 302` — Murder\n"
            "• `/ipc 376` — Rape\n"
            "• `/ipc 498A` — Cruelty by husband\n"
            "• `/ipc 354` — Assault on woman\n\n"
            "You can also look up BNS (new code) sections!",
            parse_mode="Markdown",
        )
        return

    section = " ".join(args).strip()
    await _track_user(update)
    await send_typing(update)
    await update.message.reply_text(f"📕 Looking up Section {section}...")

    try:
        result = groq_service.lookup_ipc_section(section)
        formatted = formatter.format_ipc_response(result, section)
        context.user_data["last_bot_response"] = result
        await send_long_message(update, formatted)
        await _log_conv(update, "ipc", f"/ipc {section}", result)
    except Exception as e:
        logger.error(f"IPC lookup error: {e}")
        await update.message.reply_text("❌ Sorry, I couldn't look up that section. Please try again.")


async def glossary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /glossary <term> command — explain legal terms."""
    if not _check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⏳ You're sending too many requests. Please wait a moment.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "📖 *Legal Glossary*\n\n"
            "Usage: `/glossary <term>`\n\n"
            "Examples:\n"
            "• `/glossary bail`\n"
            "• `/glossary FIR`\n"
            "• `/glossary habeas corpus`\n"
            "• `/glossary anticipatory bail`\n"
            "• `/glossary cognizable offence`\n"
            "• `/glossary writ petition`",
            parse_mode="Markdown",
        )
        return

    term = " ".join(args).strip()
    await _track_user(update)
    await send_typing(update)

    try:
        result = groq_service.explain_legal_term(term)
        formatted = formatter.format_glossary_response(result, term)
        context.user_data["last_bot_response"] = result
        await send_long_message(update, formatted)
        await _log_conv(update, "glossary", f"/glossary {term}", result)
    except Exception as e:
        logger.error(f"Glossary error: {e}")
        await update.message.reply_text("❌ Sorry, I couldn't explain that term. Please try again.")


async def hindi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /hindi command — translate last response to Hindi."""
    if not _check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⏳ You're sending too many requests. Please wait a moment.")
        return

    last_response = context.user_data.get("last_bot_response")
    if not last_response:
        await update.message.reply_text(
            "🌐 No previous response to translate.\n"
            "Ask a legal question first, then use /hindi to get the answer in Hindi."
        )
        return

    await send_typing(update)
    await update.message.reply_text("🌐 Translating to Hindi...")

    try:
        translated = groq_service.translate_to_hindi(last_response)
        await send_long_message(update, "🇮🇳 *हिंदी अनुवाद:*\n\n" + translated)
    except Exception as e:
        logger.error(f"Hindi translation error: {e}")
        await update.message.reply_text("❌ Translation failed. Please try again.")


async def telugu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /telugu command — translate last response to Telugu."""
    if not _check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⏳ You're sending too many requests. Please wait a moment.")
        return

    last_response = context.user_data.get("last_bot_response")
    if not last_response:
        await update.message.reply_text(
            "🌐 No previous response to translate.\n"
            "Ask a legal question first, then use /telugu to get the answer in Telugu."
        )
        return

    await send_typing(update)
    await update.message.reply_text("🌐 Translating to Telugu...")

    try:
        translated = groq_service.translate_to_telugu(last_response)
        await send_long_message(update, "🇮🇳 *తెలుగు అనువాదం:*\n\n" + translated)
    except Exception as e:
        logger.error(f"Telugu translation error: {e}")
        await update.message.reply_text("❌ Translation failed. Please try again.")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /history command — show recent activity from DB."""
    user = update.effective_user
    if not user:
        return

    try:
        conversations = await db.get_user_history(user.id, limit=10)
        formatted = formatter.format_history_response(conversations)
        await send_long_message(update, formatted)
    except Exception as e:
        logger.error(f"History command error: {e}")
        await update.message.reply_text("❌ Sorry, I couldn't fetch your history. Please try again.")


async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /feedback command — collect user feedback."""
    await update.message.reply_text(
        "💬 *We'd love your feedback!*\n\n"
        "Please type your feedback, suggestion, or issue below.\n"
        "Type /cancel to go back.",
        parse_mode="Markdown",
    )
    return FEEDBACK_WAITING


async def feedback_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and log user feedback."""
    feedback = update.message.text
    user = update.effective_user
    logger.info(f"FEEDBACK from {user.username or user.id}: {feedback}")

    # Save to DB
    try:
        await db.save_feedback(user.id, user.username or str(user.id), feedback)
    except Exception as e:
        logger.error(f"DB save_feedback error: {e}")

    await update.message.reply_text(
        "✅ *Thank you for your feedback!*\n\n"
        "Your input helps us make VoltLegal better for everyone. 🙏",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def feedback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel feedback."""
    await update.message.reply_text("✅ Feedback cancelled. How else can I help?")
    return ConversationHandler.END


# ─── Mode 1: Scan & Explain (PDF / Image / Word) ────────────────────────────

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle PDF document uploads → Gemini analysis."""
    if not _check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⏳ Please wait a moment before sending another document.")
        return

    await _track_user(update)
    await send_typing(update)
    await update.message.reply_text("📄 Analyzing your document... This may take a moment.")

    try:
        doc = update.message.document
        file = await context.bot.get_file(doc.file_id)
        pdf_bytes = await file.download_as_bytearray()

        result = gemini_service.analyze_pdf(bytes(pdf_bytes), doc.file_name or "document.pdf")
        formatted = formatter.format_document_analysis(result, "Document")

        # Store context for follow-up and translation
        context.user_data["last_document_analysis"] = result
        context.user_data["last_mode"] = "document"
        context.user_data["last_bot_response"] = result
        context.user_data["last_context_time"] = datetime.now()

        await send_long_message(update, formatted)
        await update.message.reply_text(
            "💬 _You can ask follow-up questions about this document. "
            "Just type your question! Use /clear to switch to general legal queries._\n"
            "🌐 _Use /hindi or /telugu to translate._",
            parse_mode="Markdown",
        )

        await _log_conv(update, "document", f"[PDF] {doc.file_name or 'document.pdf'}", result)

    except Exception as e:
        logger.error(f"PDF analysis error: {e}")
        await update.message.reply_text(
            "❌ Sorry, I couldn't analyze this document. "
            "Please make sure it's a valid PDF and try again."
        )


async def handle_word_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Word document uploads → Gemini analysis."""
    if not _check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⏳ Please wait a moment before sending another document.")
        return

    await _track_user(update)
    await send_typing(update)
    await update.message.reply_text("📄 Analyzing your Word document... This may take a moment.")

    try:
        doc = update.message.document
        file = await context.bot.get_file(doc.file_id)
        doc_bytes = await file.download_as_bytearray()

        result = gemini_service.analyze_word_doc(bytes(doc_bytes), doc.file_name or "document.docx")
        formatted = formatter.format_document_analysis(result, "Document")

        context.user_data["last_document_analysis"] = result
        context.user_data["last_mode"] = "document"
        context.user_data["last_bot_response"] = result
        context.user_data["last_context_time"] = datetime.now()

        await send_long_message(update, formatted)
        await update.message.reply_text(
            "💬 _You can ask follow-up questions about this document. "
            "Just type your question! Use /clear to switch to general legal queries._\n"
            "🌐 _Use /hindi or /telugu to translate._",
            parse_mode="Markdown",
        )

        await _log_conv(update, "document", f"[Word] {doc.file_name or 'document.docx'}", result)

    except Exception as e:
        logger.error(f"Word doc analysis error: {e}")
        await update.message.reply_text(
            "❌ Sorry, I couldn't analyze this Word document. "
            "Please try converting it to PDF and uploading again."
        )


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo uploads → Gemini Vision analysis."""
    if not _check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⏳ Please wait a moment before sending another image.")
        return

    await _track_user(update)
    await send_typing(update)
    await update.message.reply_text("📷 Reading your document image... Please wait.")

    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        img_bytes = await file.download_as_bytearray()

        result = gemini_service.analyze_image(bytes(img_bytes))
        formatted = formatter.format_document_analysis(result, "Image")

        context.user_data["last_document_analysis"] = result
        context.user_data["last_mode"] = "document"
        context.user_data["last_bot_response"] = result
        context.user_data["last_context_time"] = datetime.now()

        await send_long_message(update, formatted)
        await update.message.reply_text(
            "💬 _You can ask follow-up questions about this document. "
            "Just type your question!_\n"
            "🌐 _Use /hindi or /telugu to translate._",
            parse_mode="Markdown",
        )

        await _log_conv(update, "document", "[Image upload]", result)

    except Exception as e:
        logger.error(f"Image analysis error: {e}")
        await update.message.reply_text(
            "❌ Sorry, I couldn't analyze this image. "
            "Please ensure it's clear and readable, then try again."
        )


# ─── Voice Message Handler ──────────────────────────────────────────────────

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages — transcribe with Gemini, then answer with Groq."""
    if not _check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⏳ Please wait a moment before sending another message.")
        return

    await _track_user(update)
    await send_typing(update)
    await update.message.reply_text("🎤 Listening to your voice message...")

    try:
        voice = update.message.voice or update.message.audio
        file = await context.bot.get_file(voice.file_id)
        audio_bytes = await file.download_as_bytearray()

        # Determine mime type
        mime_type = voice.mime_type if voice.mime_type else "audio/ogg"

        # Transcribe with Gemini
        transcription = gemini_service.transcribe_voice(bytes(audio_bytes), mime_type)

        if not transcription or not transcription.strip():
            await update.message.reply_text(
                "❌ I couldn't understand the voice message. "
                "Please try speaking more clearly or type your question instead."
            )
            return

        # Show transcription
        await update.message.reply_text(
            f"🎤 *I heard:* _{transcription.strip()}_",
            parse_mode="Markdown",
        )

        # Now process it as a legal question
        await send_typing(update)

        # Check if there's document context for follow-up
        last_analysis = context.user_data.get("last_document_analysis")
        last_mode = context.user_data.get("last_mode")

        if last_mode == "document" and last_analysis:
            await update.message.reply_text("💬 Looking into your question about the document...")
            result = groq_service.ask_document_followup(transcription, last_analysis)
            formatted = formatter.format_legal_response(result)
        else:
            await update.message.reply_text("⚖️ Looking up the law for you...")
            result = groq_service.ask_legal_question(transcription)
            formatted = formatter.format_info_response(result)

        context.user_data["last_bot_response"] = result
        await send_long_message(update, formatted)

        await _log_conv(update, "voice", f"[Voice] {transcription.strip()}", result)

    except Exception as e:
        logger.error(f"Voice message error: {e}")
        await update.message.reply_text(
            "❌ Sorry, I couldn't process your voice message. "
            "Please try typing your question instead."
        )


# ─── Mode 2: Situation Help (ConversationHandler) ───────────────────────────

async def situation_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the situation help flow with /situation command."""
    await _track_user(update)
    context.user_data["situation_history"] = []
    context.user_data["last_mode"] = "situation"
    context.user_data["situation_messages_count"] = 0

    # Check for previous session to resume
    try:
        user = update.effective_user
        last_session = await db.get_last_session(user.id, "situation")
        if last_session and last_session.get("history_json"):
            created = last_session.get("created_at", "unknown date")
            summary = last_session.get("summary", "previous situation")
            await update.message.reply_text(
                f"📂 I found a previous situation session from *{created}*:\n"
                f"_{summary}_\n\n"
                "Would you like to *continue* that session or *start fresh*?\n"
                "Type `continue` or `fresh`.",
                parse_mode="Markdown",
            )
            context.user_data["_pending_resume_session"] = last_session
            return SITUATION_GATHERING
    except Exception as e:
        logger.error(f"Session resume check error: {e}")

    try:
        await send_typing(update)
        intake_msg = groq_service.start_situation_intake()
        context.user_data["situation_history"].append(
            {"role": "assistant", "content": intake_msg}
        )
        await send_long_message(
            update,
            "🛡️ *Situation Help Mode*\n\n" + intake_msg +
            "\n\n_Type /cancel to exit this mode._",
        )
    except Exception as e:
        logger.error(f"Situation start error: {e}")
        await update.message.reply_text(
            "❌ Sorry, I couldn't start the situation analysis. Please try again."
        )
        return ConversationHandler.END

    return SITUATION_GATHERING


async def situation_gather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gather details about the user's situation."""
    if not _check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⏳ Please wait a moment.")
        return SITUATION_GATHERING

    user_msg = update.message.text

    # Handle session resume
    pending = context.user_data.pop("_pending_resume_session", None)
    if pending:
        lower = user_msg.lower().strip()
        if lower in ("continue", "resume", "yes", "haan", "ha"):
            try:
                old_history = json.loads(pending["history_json"])
                context.user_data["situation_history"] = old_history
                context.user_data["situation_messages_count"] = len(
                    [m for m in old_history if m.get("role") == "user"]
                )
                await update.message.reply_text(
                    "✅ *Session restored!* Here's where we left off. "
                    "Please continue with more details or ask a question.\n\n"
                    "_Type /cancel to exit._",
                    parse_mode="Markdown",
                )
                return SITUATION_GATHERING
            except Exception as e:
                logger.error(f"Session restore error: {e}")
                await update.message.reply_text("❌ Couldn't restore session. Starting fresh.")

        # Start fresh
        try:
            await send_typing(update)
            intake_msg = groq_service.start_situation_intake()
            context.user_data["situation_history"] = [
                {"role": "assistant", "content": intake_msg}
            ]
            await send_long_message(
                update,
                "🛡️ *Situation Help Mode*\n\n" + intake_msg +
                "\n\n_Type /cancel to exit this mode._",
            )
            return SITUATION_GATHERING
        except Exception as e:
            logger.error(f"Situation fresh start error: {e}")
            await update.message.reply_text("❌ Error starting situation mode. Try again.")
            return ConversationHandler.END

    history = context.user_data.get("situation_history", [])
    history.append({"role": "user", "content": user_msg})
    context.user_data["situation_messages_count"] = \
        context.user_data.get("situation_messages_count", 0) + 1

    try:
        await send_typing(update)

        if context.user_data["situation_messages_count"] >= 3:
            await update.message.reply_text("🔍 Analyzing your situation...")
            result = groq_service.analyze_situation(history)
            formatted = formatter.format_situation_response(result)
            context.user_data["last_bot_response"] = result
            await send_long_message(update, formatted)

            await _log_conv(update, "situation", user_msg, result)

            await update.message.reply_text(
                "💬 _Do you have more details or another question about this situation? "
                "Type /cancel when you're done._\n"
                "🌐 _Use /hindi or /telugu to translate._",
                parse_mode="Markdown",
            )
            return SITUATION_FOLLOWUP
        else:
            response = groq_service.continue_situation_intake(history)
            history.append({"role": "assistant", "content": response})
            context.user_data["situation_history"] = history
            await send_long_message(update, response)
            return SITUATION_GATHERING

    except Exception as e:
        logger.error(f"Situation gather error: {e}")
        await update.message.reply_text(
            "❌ An error occurred. Please try again or type /cancel to exit."
        )
        return SITUATION_GATHERING


async def situation_followup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle follow-up questions during situation help."""
    if not _check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⏳ Please wait a moment.")
        return SITUATION_FOLLOWUP

    user_msg = update.message.text
    history = context.user_data.get("situation_history", [])
    history.append({"role": "user", "content": user_msg})
    context.user_data["situation_history"] = history

    try:
        await send_typing(update)
        await update.message.reply_text("💬 Looking into that...")
        result = groq_service.answer_situation_followup(history)
        formatted = formatter.format_legal_response(result)
        history.append({"role": "assistant", "content": result})
        context.user_data["situation_history"] = history
        context.user_data["last_bot_response"] = result
        await send_long_message(update, formatted)

        await _log_conv(update, "situation", user_msg, result)

        return SITUATION_FOLLOWUP

    except Exception as e:
        logger.error(f"Situation followup error: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")
        return SITUATION_FOLLOWUP


async def situation_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the situation help flow."""
    # Save session to DB before clearing
    history = context.user_data.get("situation_history")
    if history:
        try:
            user = update.effective_user
            summary = "Situation help session"
            # Try to extract a brief summary from first user message
            user_msgs = [m["content"] for m in history if m.get("role") == "user"]
            if user_msgs:
                summary = user_msgs[0][:100]
            await db.save_session(user.id, "situation", json.dumps(history), summary)
        except Exception as e:
            logger.error(f"Session save error: {e}")

    context.user_data.pop("situation_history", None)
    context.user_data.pop("situation_messages_count", None)
    context.user_data["last_mode"] = None
    await update.message.reply_text(
        "✅ Situation help ended.\n\n"
        "You can:\n"
        "📄 Send a document to analyze\n"
        "📚 Ask any legal question\n"
        "🛡️ Use /situation to describe a new situation\n"
        "✍️ Use /draft to draft a legal document"
    )
    return ConversationHandler.END


# ─── Mode 4: Document Drafting (ConversationHandler) ─────────────────────────

async def draft_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the document drafting flow."""
    await _track_user(update)
    context.user_data["draft_history"] = []
    context.user_data["draft_messages_count"] = 0

    # Check for previous session to resume
    try:
        user = update.effective_user
        last_session = await db.get_last_session(user.id, "draft")
        if last_session and last_session.get("history_json"):
            created = last_session.get("created_at", "unknown date")
            summary = last_session.get("summary", "previous draft")
            await update.message.reply_text(
                f"📂 I found a previous draft session from *{created}*:\n"
                f"_{summary}_\n\n"
                "Would you like to *continue* that session or *start fresh*?\n"
                "Type `continue` or `fresh`.",
                parse_mode="Markdown",
            )
            context.user_data["_pending_resume_draft"] = last_session
            return DRAFT_GATHERING
    except Exception as e:
        logger.error(f"Draft session resume check error: {e}")

    try:
        await send_typing(update)
        intake_msg = groq_service.start_draft_intake()
        context.user_data["draft_history"].append(
            {"role": "assistant", "content": intake_msg}
        )
        await send_long_message(
            update,
            "✍️ *Document Drafting Mode*\n\n" + intake_msg +
            "\n\n_Type /cancel to exit this mode._",
        )
    except Exception as e:
        logger.error(f"Draft start error: {e}")
        await update.message.reply_text(
            "❌ Sorry, I couldn't start drafting. Please try again."
        )
        return ConversationHandler.END

    return DRAFT_GATHERING


async def _generate_and_send_draft(update, context, history, user_msg):
    """Helper: generate draft, send it, log to DB."""
    await update.message.reply_text("📝 Generating your draft...")
    result = groq_service.generate_draft(history)
    formatted = formatter.format_draft_response(result)
    context.user_data["last_bot_response"] = result
    await send_long_message(update, formatted)

    await _log_conv(update, "draft", user_msg, result)

    await update.message.reply_text(
        "💬 _Want me to modify anything in this draft? Just tell me. "
        "Type /cancel when you're done._\n"
        "🌐 _Use /hindi or /telugu to translate._",
        parse_mode="Markdown",
    )


async def draft_gather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gather information for the document draft with smart trigger."""
    if not _check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⏳ Please wait a moment.")
        return DRAFT_GATHERING

    user_msg = update.message.text

    # Handle session resume
    pending = context.user_data.pop("_pending_resume_draft", None)
    if pending:
        lower = user_msg.lower().strip()
        if lower in ("continue", "resume", "yes", "haan", "ha"):
            try:
                old_history = json.loads(pending["history_json"])
                context.user_data["draft_history"] = old_history
                context.user_data["draft_messages_count"] = len(
                    [m for m in old_history if m.get("role") == "user"]
                )
                await update.message.reply_text(
                    "✅ *Session restored!* Continue providing details "
                    "or type `generate` when ready.\n\n"
                    "_Type /cancel to exit._",
                    parse_mode="Markdown",
                )
                return DRAFT_GATHERING
            except Exception as e:
                logger.error(f"Draft session restore error: {e}")
                await update.message.reply_text("❌ Couldn't restore session. Starting fresh.")

        # Start fresh
        try:
            await send_typing(update)
            intake_msg = groq_service.start_draft_intake()
            context.user_data["draft_history"] = [
                {"role": "assistant", "content": intake_msg}
            ]
            await send_long_message(
                update,
                "✍️ *Document Drafting Mode*\n\n" + intake_msg +
                "\n\n_Type /cancel to exit this mode._",
            )
            return DRAFT_GATHERING
        except Exception as e:
            logger.error(f"Draft fresh start error: {e}")
            await update.message.reply_text("❌ Error starting draft mode. Try again.")
            return ConversationHandler.END

    history = context.user_data.get("draft_history", [])
    history.append({"role": "user", "content": user_msg})
    context.user_data["draft_messages_count"] = \
        context.user_data.get("draft_messages_count", 0) + 1

    try:
        await send_typing(update)

        # Check for keyword triggers
        lower_msg = user_msg.lower().strip()
        keyword_triggered = any(kw in lower_msg for kw in DRAFT_TRIGGER_KEYWORDS)

        if keyword_triggered:
            await _generate_and_send_draft(update, context, history, user_msg)
            return DRAFT_READY

        # Smart readiness check via Groq (only after at least 2 exchanges)
        if context.user_data["draft_messages_count"] >= 2:
            try:
                readiness = groq_service.check_draft_readiness(history)
                if "READY" in readiness:
                    await _generate_and_send_draft(update, context, history, user_msg)
                    return DRAFT_READY
            except Exception as e:
                logger.warning(f"Draft readiness check failed: {e}")

        # Not ready yet — continue gathering
        response = groq_service.continue_draft_intake(history)
        history.append({"role": "assistant", "content": response})
        context.user_data["draft_history"] = history
        await send_long_message(update, response)
        return DRAFT_GATHERING

    except Exception as e:
        logger.error(f"Draft gather error: {e}")
        await update.message.reply_text(
            "❌ An error occurred. Please try again or type /cancel to exit."
        )
        return DRAFT_GATHERING


async def draft_followup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle revision requests for the generated draft."""
    if not _check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⏳ Please wait a moment.")
        return DRAFT_READY

    user_msg = update.message.text
    history = context.user_data.get("draft_history", [])
    history.append({"role": "user", "content": user_msg})

    try:
        await send_typing(update)
        await update.message.reply_text("📝 Updating your draft...")
        result = groq_service.generate_draft(history)
        formatted = formatter.format_draft_response(result)
        context.user_data["last_bot_response"] = result
        await send_long_message(update, formatted)

        await _log_conv(update, "draft", user_msg, result)

        return DRAFT_READY

    except Exception as e:
        logger.error(f"Draft followup error: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")
        return DRAFT_READY


async def draft_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the drafting flow."""
    # Save session to DB before clearing
    history = context.user_data.get("draft_history")
    if history:
        try:
            user = update.effective_user
            summary = "Draft session"
            user_msgs = [m["content"] for m in history if m.get("role") == "user"]
            if user_msgs:
                summary = user_msgs[0][:100]
            await db.save_session(user.id, "draft", json.dumps(history), summary)
        except Exception as e:
            logger.error(f"Draft session save error: {e}")

    context.user_data.pop("draft_history", None)
    context.user_data.pop("draft_messages_count", None)
    await update.message.reply_text(
        "✅ Drafting ended.\n\n"
        "You can:\n"
        "📄 Send a document to analyze\n"
        "📚 Ask any legal question\n"
        "🛡️ Use /situation to describe a legal situation\n"
        "✍️ Use /draft to draft another document"
    )
    return ConversationHandler.END


# ─── Mode 3: Legal Info + Document Follow-up (Text) ─────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages — legal Q&A or document follow-up."""
    if not _check_rate_limit(update.effective_user.id):
        await update.message.reply_text(
            "⏳ You're sending too many requests. Please wait a moment before trying again."
        )
        return

    user_msg = update.message.text

    if not user_msg or not user_msg.strip():
        return

    # ─── Auto-clear stale context ────────────────────────────────────────
    last_ctx_time = context.user_data.get("last_context_time")
    if last_ctx_time and isinstance(last_ctx_time, datetime):
        if datetime.now() - last_ctx_time > timedelta(hours=CONTEXT_EXPIRY_HOURS):
            context.user_data.pop("last_document_analysis", None)
            context.user_data.pop("last_bot_response", None)
            context.user_data.pop("last_context_time", None)
            context.user_data["last_mode"] = None
            await update.message.reply_text(
                "🔄 Your previous document context has expired. "
                "This will be treated as a fresh query."
            )

    # Check for inline translation requests
    lower_msg = user_msg.lower().strip()
    if lower_msg in ("translate", "hindi", "hindi me batao", "hindi mein batao", "हिंदी"):
        last_response = context.user_data.get("last_bot_response")
        if last_response:
            await send_typing(update)
            await update.message.reply_text("🌐 Translating to Hindi...")
            try:
                translated = groq_service.translate_to_hindi(last_response)
                await send_long_message(update, "🇮🇳 *हिंदी अनुवाद:*\n\n" + translated)
            except Exception as e:
                logger.error(f"Hindi translation error: {e}")
                await update.message.reply_text("❌ Translation failed. Please try again.")
        else:
            await update.message.reply_text(
                "🌐 No previous response to translate. Ask a question first!"
            )
        return

    if lower_msg in ("telugu", "telugu lo cheppu", "telugu lo", "తెలుగు"):
        last_response = context.user_data.get("last_bot_response")
        if last_response:
            await send_typing(update)
            await update.message.reply_text("🌐 Translating to Telugu...")
            try:
                translated = groq_service.translate_to_telugu(last_response)
                await send_long_message(update, "🇮🇳 *తెలుగు అనువాదం:*\n\n" + translated)
            except Exception as e:
                logger.error(f"Telugu translation error: {e}")
                await update.message.reply_text("❌ Translation failed. Please try again.")
        else:
            await update.message.reply_text(
                "🌐 No previous response to translate. Ask a question first!"
            )
        return

    await _track_user(update)

    # Check if this is a follow-up to a document analysis
    last_analysis = context.user_data.get("last_document_analysis")
    last_mode = context.user_data.get("last_mode")

    if last_mode == "document" and last_analysis:
        await send_typing(update)
        await update.message.reply_text("💬 Looking into your question about the document...")
        try:
            result = groq_service.ask_document_followup(user_msg, last_analysis)
            formatted = formatter.format_legal_response(result)
            context.user_data["last_bot_response"] = result
            await send_long_message(update, formatted)
            await _log_conv(update, "document", user_msg, result)
        except Exception as e:
            logger.error(f"Document followup error: {e}")
            await update.message.reply_text("❌ An error occurred. Please try again.")
        return

    # Default: Legal information question (Mode 3)
    await send_typing(update)
    await update.message.reply_text("⚖️ Looking up the law for you...")
    try:
        result = groq_service.ask_legal_question(user_msg)
        formatted = formatter.format_info_response(result)
        context.user_data["last_bot_response"] = result
        await send_long_message(update, formatted)
        await _log_conv(update, "legal_qa", user_msg, result)
    except Exception as e:
        logger.error(f"Legal Q&A error: {e}")
        await update.message.reply_text(
            "❌ Sorry, I couldn't process your question. Please try rephrasing."
        )


# ─── Forwarded Message Handler ──────────────────────────────────────────────

async def handle_forwarded(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle forwarded text messages — analyze them as legal documents."""
    if not _check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⏳ Please wait a moment.")
        return

    forwarded_text = update.message.text
    if not forwarded_text or not forwarded_text.strip():
        return

    await _track_user(update)
    await send_typing(update)
    await update.message.reply_text("📨 Analyzing the forwarded message for legal content...")

    try:
        result = groq_service.ask_legal_question(
            f"Analyze this text for any legal implications, rights, or relevant laws:\n\n{forwarded_text}"
        )
        formatted = formatter.format_legal_response(result)
        context.user_data["last_bot_response"] = result
        await send_long_message(update, formatted)
        await _log_conv(update, "legal_qa", f"[Forwarded] {forwarded_text[:200]}", result)
    except Exception as e:
        logger.error(f"Forwarded message error: {e}")
        await update.message.reply_text("❌ Sorry, I couldn't analyze this message.")


# ─── Clear Context Command ──────────────────────────────────────────────────

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear the document context so new questions are treated as fresh legal queries."""
    context.user_data.pop("last_document_analysis", None)
    context.user_data.pop("last_bot_response", None)
    context.user_data.pop("last_context_time", None)
    context.user_data["last_mode"] = None
    await update.message.reply_text(
        "🔄 Context cleared! Your next question will be treated as a fresh legal query.\n\n"
        "You can:\n"
        "📄 Send a document to analyze\n"
        "📚 Ask any legal question\n"
        "🛡️ Use /situation to describe a legal situation\n"
        "✍️ Use /draft to draft a legal document"
    )


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    """Start the VoltLegal bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not found in .env")
        print("   Get one from @BotFather on Telegram and add it to your .env file.")
        return

    print("⚖️  VoltLegal is starting...")

    # Initialize database
    asyncio.run(db.init_db())

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Situation help conversation handler (Mode 2)
    situation_handler = ConversationHandler(
        entry_points=[CommandHandler("situation", situation_start)],
        states={
            SITUATION_GATHERING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, situation_gather),
            ],
            SITUATION_FOLLOWUP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, situation_followup),
            ],
        },
        fallbacks=[CommandHandler("cancel", situation_cancel)],
    )

    # Document drafting conversation handler (Mode 4)
    draft_handler = ConversationHandler(
        entry_points=[CommandHandler("draft", draft_start)],
        states={
            DRAFT_GATHERING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, draft_gather),
            ],
            DRAFT_READY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, draft_followup),
            ],
        },
        fallbacks=[CommandHandler("cancel", draft_cancel)],
    )

    # Feedback conversation handler
    feedback_handler = ConversationHandler(
        entry_points=[CommandHandler("feedback", feedback_start)],
        states={
            FEEDBACK_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_receive),
            ],
        },
        fallbacks=[CommandHandler("cancel", feedback_cancel)],
    )

    # Register handlers (order matters!)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rights", rights_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("ipc", ipc_command))
    app.add_handler(CommandHandler("glossary", glossary_command))
    app.add_handler(CommandHandler("hindi", hindi_command))
    app.add_handler(CommandHandler("telugu", telugu_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("clear", clear_command))

    # Conversation handlers
    app.add_handler(situation_handler)
    app.add_handler(draft_handler)
    app.add_handler(feedback_handler)

    # Mode 1: Document/Image uploads
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
    word_filter = (
        filters.Document.MimeType("application/vnd.openxmlformats-officedocument.wordprocessingml.document") |
        filters.Document.MimeType("application/msword")
    )
    app.add_handler(MessageHandler(word_filter, handle_word_doc))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))

    # Voice messages
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    # Forwarded text messages
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.FORWARDED,
        handle_forwarded,
    ))

    # Mode 3: Text questions (+ document follow-up)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("✅ VoltLegal is running! Send messages on Telegram.")
    print("   Features: Legal Q&A, Document Scan, Situation Help, Drafting,")
    print("   IPC Lookup, Glossary, Voice Messages, Hindi & Telugu Translation")
    print("   Database: SQLite persistent storage enabled")
    keep_alive()
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
