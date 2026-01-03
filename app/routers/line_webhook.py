"""LINE Webhook router with proper async handling for MongoDB."""

import logging
import time
import asyncio
from fastapi import APIRouter, Request, HTTPException, Header
from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    MessageEvent,
    ImageMessageContent,
    TextMessageContent,
    FileMessageContent,
)
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging.exceptions import ApiException as LineApiException
from azure.core.exceptions import HttpResponseError

from app.config import settings
from app.services.ocr_service import ocr_service
from app.services.chat_service import chat_service
from app.models.message import MessageType
from app.repositories.user_repository import user_repository
from app.repositories.message_repository import message_repository
from app.utils.rate_limiter import text_rate_limiter, image_rate_limiter, pdf_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/line", tags=["LINE"])

# LINE SDK setup
configuration = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(settings.LINE_CHANNEL_SECRET)

# Constants for message splitting
MAX_CHARS_PER_MESSAGE = 2000  # Safe limit for LINE (actual limit is 5000)
MAX_MESSAGES_PER_REPLY = 5    # LINE allows max 5 messages per reply


def split_text_to_chunks(text: str, max_chars: int = MAX_CHARS_PER_MESSAGE) -> list[str]:
    """
    Split text into chunks that fit within LINE message limits.
    Tries to split at newlines or spaces for better readability.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        # Find a good split point (prefer newline, then space)
        split_point = max_chars

        # Look for newline within last 200 chars of the chunk
        newline_pos = remaining.rfind('\n', max_chars - 200, max_chars)
        if newline_pos > 0:
            split_point = newline_pos + 1
        else:
            # Look for space within last 100 chars
            space_pos = remaining.rfind(' ', max_chars - 100, max_chars)
            if space_pos > 0:
                split_point = space_pos + 1

        chunks.append(remaining[:split_point].rstrip())
        remaining = remaining[split_point:].lstrip()

    return chunks


def send_reply(reply_token: str, text: str):
    """Send a reply message to LINE (sync helper)."""
    try:
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=text)],
                )
            )
    except LineApiException as e:
        logger.error(f"Failed to send reply: {e}")


def send_reply_multi(reply_token: str, texts: list[str]):
    """
    Send multiple messages in one reply (max 5 messages).
    Use this for long OCR results that need to be split.
    """
    try:
        # Limit to max 5 messages
        texts_to_send = texts[:MAX_MESSAGES_PER_REPLY]

        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            messages = [TextMessage(text=t) for t in texts_to_send]
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=messages,
                )
            )

        if len(texts) > MAX_MESSAGES_PER_REPLY:
            logger.warning(
                f"Text was too long, only sent {MAX_MESSAGES_PER_REPLY} of {len(texts)} chunks"
            )

    except LineApiException as e:
        logger.error(f"Failed to send multi reply: {e}")


def get_message_content(message_id: str) -> bytes:
    """Get message content from LINE (sync helper)."""
    with ApiClient(configuration) as api_client:
        blob_api = MessagingApiBlob(api_client)
        return blob_api.get_message_content(message_id)


@router.post("/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: str = Header(..., alias="X-Line-Signature"),
):
    """LINE Webhook endpoint - processes events asynchronously in main event loop."""
    body = await request.body()
    body_str = body.decode("utf-8")

    try:
        # Parse events using LINE SDK
        events = parser.parse(body_str, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Process each event asynchronously (in main event loop - compatible with Motor)
    for event in events:
        if isinstance(event, MessageEvent):
            if isinstance(event.message, ImageMessageContent):
                asyncio.create_task(process_image_message(event))
            elif isinstance(event.message, TextMessageContent):
                asyncio.create_task(process_text_message(event))
            elif isinstance(event.message, FileMessageContent):
                asyncio.create_task(process_file_message(event))

    # Return immediately to LINE (required within 1 second)
    return {"status": "ok"}


async def process_image_message(event: MessageEvent):
    """Process image message asynchronously."""
    message_id = event.message.id
    reply_token = event.reply_token
    line_user_id = event.source.user_id

    # Check rate limit
    allowed, _ = image_rate_limiter.is_allowed(line_user_id)
    if not allowed:
        logger.warning(f"Rate limit exceeded for user {line_user_id} (image)")
        send_reply(
            reply_token,
            "⚠️ RATE LIMIT EXCEEDED\n\n"
            "คุณส่งรูปภาพบ่อยเกินไป\n"
            "กรุณารอสักครู่แล้วลองใหม่\n\n"
            "Limit: 5 images per minute"
        )
        return

    try:
        # Get or create user in database (async - runs in main loop)
        user = await user_repository.get_or_create_user(line_user_id)
        await user_repository.increment_message_count(user)

        # Get image content from LINE (sync operation)
        image_content = await asyncio.to_thread(get_message_content, message_id)

        # Validate image content
        if not image_content:
            raise ValueError("Empty image content received")

        content_size = len(image_content)
        logger.info(f"Received image: message_id={message_id}, size={content_size} bytes")

        # Check size limit (10MB)
        if content_size > 10 * 1024 * 1024:
            raise ValueError("Image size exceeds 10MB limit")

        if content_size < 100:
            raise ValueError("Image content too small, might be corrupted")

        logger.info(f"Starting OCR processing for message_id={message_id}")

        # Track processing time
        start_time = time.time()

        # Perform OCR on the image (sync operation - run in thread)
        extracted_text = await asyncio.to_thread(
            ocr_service.extract_text_from_bytes, image_content
        )

        processing_time = time.time() - start_time

        logger.info(
            f"OCR completed: message_id={message_id}, text_length={len(extracted_text)}, time={processing_time:.2f}s"
        )

        # Format response
        size_kb = content_size / 1024
        size_mb = size_kb / 1024
        size_display = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{size_kb:.2f} KB"

        # Save message to database (async)
        await message_repository.create_message(
            user=user,
            message_type=MessageType.IMAGE,
            content=extracted_text,
            metadata={
                "image_size": content_size,
                "processing_time": processing_time,
                "line_message_id": message_id,
            },
            line_message_id=message_id,
        )

        # Build messages - split long text into multiple messages
        if not extracted_text.strip():
            # No text found
            result_text = (
                f"📸 IMAGE OCR RESULT\n"
                f"{'='*30}\n\n"
                f"ไม่พบข้อความในรูปภาพ\n\n"
                f"{'='*30}\n"
                f"📏 Size: {size_display}\n"
                f"⏱️ Processing: {processing_time:.2f}s"
            )
            await asyncio.to_thread(send_reply, reply_token, result_text)
        else:
            # Split text into chunks for multiple messages
            text_chunks = split_text_to_chunks(extracted_text, MAX_CHARS_PER_MESSAGE - 100)
            total_chunks = len(text_chunks)

            messages = []

            # First message: Header + first chunk
            header = (
                f"📸 IMAGE OCR RESULT\n"
                f"{'='*30}\n"
                f"📏 Size: {size_display} | 📝 {len(extracted_text)} chars\n"
                f"⏱️ Processing: {processing_time:.2f}s\n"
            )
            if total_chunks > 1:
                header += f"📄 แบ่งเป็น {total_chunks} ข้อความ\n"
            header += f"{'='*30}\n\n"

            first_msg = header + text_chunks[0]
            messages.append(first_msg)

            # Additional chunks (messages 2-5)
            for i, chunk in enumerate(text_chunks[1:MAX_MESSAGES_PER_REPLY], start=2):
                chunk_msg = f"📸 ต่อ ({i}/{total_chunks})\n{'─'*20}\n\n{chunk}"
                messages.append(chunk_msg)

            # Check if we couldn't send all text
            if total_chunks > MAX_MESSAGES_PER_REPLY:
                remaining_chars = sum(len(c) for c in text_chunks[MAX_MESSAGES_PER_REPLY:])
                messages[-1] += f"\n\n⚠️ ยังเหลืออีก {remaining_chars} ตัวอักษร (ไม่สามารถส่งทั้งหมดได้)"

            # Send all messages
            await asyncio.to_thread(send_reply_multi, reply_token, messages)

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        await asyncio.to_thread(
            send_reply, reply_token, f"⚠️ VALIDATION ERROR\n\n{str(e)}"
        )
    except Exception as e:
        logger.error(f"Error processing image: {e}", exc_info=True)
        try:
            await asyncio.to_thread(
                send_reply, reply_token,
                f"⚠️ ERROR\n\nFailed to process image: {str(e)[:300]}"
            )
        except Exception:
            logger.error("Cannot send error message - reply token might be used")


async def process_text_message(event: MessageEvent):
    """Process text message asynchronously."""
    reply_token = event.reply_token
    user_text = event.message.text
    line_user_id = event.source.user_id

    logger.info(f"Received text message from {line_user_id}: {user_text[:50]}...")

    # Check rate limit
    allowed, _ = text_rate_limiter.is_allowed(line_user_id)
    if not allowed:
        logger.warning(f"Rate limit exceeded for user {line_user_id} (text)")
        send_reply(
            reply_token,
            "⚠️ RATE LIMIT EXCEEDED\n\n"
            "คุณส่งข้อความบ่อยเกินไป\n"
            "กรุณารอสักครู่แล้วลองใหม่\n\n"
            "Limit: 10 messages per minute"
        )
        return

    try:
        # Get or create user in database (async)
        user = await user_repository.get_or_create_user(line_user_id)
        await user_repository.increment_message_count(user)

        # Get chatbot response with database history (async)
        bot_response = await chat_service.chat(user=user, message=user_text)

        # Validate bot response
        if not bot_response or not bot_response.strip():
            logger.warning("Empty bot response, using fallback")
            bot_response = (
                "สวัสดีครับ! ผมเป็น OCR Assistant 📄\n\n"
                "ส่งรูปภาพหรือไฟล์ PDF มาให้ผมช่วยแปลงเป็นข้อความได้เลยนะครับ!"
            )

        logger.info(f"Bot response length: {len(bot_response)}")

        # Format response
        response_text = (
            f"💬 OCR Assistant\n\n{bot_response}\n\n"
            f"───────────────\n"
            f"📸 ส่งรูปภาพมาแปลงข้อความได้เลย\n"
            f"📄 ส่ง PDF มาแปลง 10 หน้าแรกได้"
        )

        # Send reply (sync operation - run in thread)
        await asyncio.to_thread(send_reply, reply_token, response_text)

    except LineApiException as e:
        logger.error(f"LINE API error in text handler: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Error handling text message: {e}", exc_info=True)
        try:
            fallback_text = (
                "💬 OCR Assistant\n\n"
                "สวัสดีครับ! ผมเป็น OCR Assistant ที่ช่วยแปลงเอกสารเป็นข้อความ\n\n"
                "📸 ส่งรูปภาพมาแปลงข้อความได้เลย\n"
                "📄 ส่ง PDF มาแปลง 10 หน้าแรกได้"
            )
            await asyncio.to_thread(send_reply, reply_token, fallback_text)
        except Exception:
            logger.error("Cannot send fallback message - reply token already used")


async def process_file_message(event: MessageEvent):
    """Process file message (PDF) asynchronously."""
    message_id = event.message.id
    reply_token = event.reply_token
    file_name = event.message.file_name
    file_size = event.message.file_size
    line_user_id = event.source.user_id

    logger.info(f"Received file from {line_user_id}: {file_name}, size={file_size} bytes")

    # Check rate limit
    allowed, _ = pdf_rate_limiter.is_allowed(line_user_id)
    if not allowed:
        logger.warning(f"Rate limit exceeded for user {line_user_id} (pdf)")
        send_reply(
            reply_token,
            "⚠️ RATE LIMIT EXCEEDED\n\n"
            "คุณส่ง PDF บ่อยเกินไป\n"
            "กรุณารอสักครู่แล้วลองใหม่\n\n"
            "Limit: 3 PDFs per minute"
        )
        return

    try:
        # Get or create user in database (async)
        user = await user_repository.get_or_create_user(line_user_id)
        await user_repository.increment_message_count(user)

        # Check if PDF
        if not file_name.lower().endswith(".pdf"):
            send_reply(
                reply_token,
                "⚠️ INVALID FILE TYPE\n\n"
                "Sorry, I only accept PDF files.\n"
                "Please send a PDF document."
            )
            return

        # Get file content from LINE (sync operation - run in thread)
        file_content = await asyncio.to_thread(get_message_content, message_id)

        # Validate file content
        if not file_content:
            raise ValueError("Empty file content received")

        content_size = len(file_content)
        logger.info(f"PDF file size: {content_size} bytes")

        # Check size limit (100MB since we extract first 10 pages only)
        if content_size > 100 * 1024 * 1024:
            raise ValueError(
                "ไฟล์ PDF ใหญ่เกิน 100MB\n\n"
                "กรุณาลดขนาดไฟล์หรือแยกเป็นหลายไฟล์ค่ะ"
            )

        if content_size < 100:
            raise ValueError("ไฟล์ PDF เสียหายหรือว่างเปล่า")

        logger.info(f"Starting OCR processing for PDF: {file_name} (first 10 pages)")

        # Track processing time
        start_time = time.time()

        # Perform OCR on the PDF (sync operation - run in thread)
        max_pages = 10
        extracted_text = await asyncio.to_thread(
            ocr_service.extract_text_from_pdf_bytes, file_content, max_pages
        )

        processing_time = time.time() - start_time

        # Count actual pages processed
        pages_processed = extracted_text.count("━━━━━ หน้า")

        logger.info(
            f"OCR completed: pages={pages_processed}, text_length={len(extracted_text)}, time={processing_time:.2f}s"
        )

        # Format response
        size_kb = content_size / 1024
        size_mb = size_kb / 1024
        size_display = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{size_kb:.2f} KB"

        # Save message to database (async)
        await message_repository.create_message(
            user=user,
            message_type=MessageType.PDF,
            content=extracted_text,
            metadata={
                "file_name": file_name,
                "file_size": content_size,
                "pages_processed": pages_processed,
                "max_pages": max_pages,
                "processing_time": processing_time,
                "line_message_id": message_id,
            },
            line_message_id=message_id,
        )

        # Build messages - split long text into multiple messages
        if not extracted_text.strip():
            # No text found
            result_text = (
                f"📄 PDF OCR RESULT\n"
                f"{'='*30}\n"
                f"📎 File: {file_name}\n"
                f"📖 Pages: {pages_processed} หน้า\n"
                f"{'='*30}\n\n"
                f"ไม่พบข้อความใน PDF\n\n"
                f"{'='*30}\n"
                f"📏 Size: {size_display}\n"
                f"⏱️ Processing: {processing_time:.2f}s"
            )
            await asyncio.to_thread(send_reply, reply_token, result_text)
        else:
            # Split text into chunks for multiple messages
            text_chunks = split_text_to_chunks(extracted_text, MAX_CHARS_PER_MESSAGE - 100)
            total_chunks = len(text_chunks)

            messages = []

            # First message: Header + first chunk
            header = (
                f"📄 PDF OCR RESULT\n"
                f"{'='*30}\n"
                f"📎 {file_name}\n"
                f"📖 {pages_processed} หน้า | 📏 {size_display}\n"
                f"📝 {len(extracted_text)} chars | ⏱️ {processing_time:.2f}s\n"
            )
            if total_chunks > 1:
                header += f"📄 แบ่งเป็น {total_chunks} ข้อความ\n"
            header += f"{'='*30}\n\n"

            first_msg = header + text_chunks[0]
            messages.append(first_msg)

            # Additional chunks (messages 2-5)
            for i, chunk in enumerate(text_chunks[1:MAX_MESSAGES_PER_REPLY], start=2):
                chunk_msg = f"📄 ต่อ ({i}/{total_chunks})\n{'─'*20}\n\n{chunk}"
                messages.append(chunk_msg)

            # Check if we couldn't send all text
            if total_chunks > MAX_MESSAGES_PER_REPLY:
                remaining_chars = sum(len(c) for c in text_chunks[MAX_MESSAGES_PER_REPLY:])
                messages[-1] += f"\n\n⚠️ ยังเหลืออีก {remaining_chars} ตัวอักษร (ไม่สามารถส่งทั้งหมดได้)"

            # Send all messages
            await asyncio.to_thread(send_reply_multi, reply_token, messages)

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        try:
            await asyncio.to_thread(
                send_reply, reply_token, f"⚠️ ข้อผิดพลาดในการตรวจสอบ\n\n{str(e)}"
            )
        except Exception:
            logger.error("Cannot send error message - reply token might be used")
    except HttpResponseError as e:
        logger.error(f"Azure API error: {e}", exc_info=True)
        try:
            error_msg = "⚠️ AZURE OCR ERROR\n\nไม่สามารถประมวลผล PDF ได้\n\n"

            if "InvalidContentLength" in str(e) or "too large" in str(e).lower():
                error_msg += (
                    "ไฟล์มีขนาดใหญ่เกินไป หรือมีเนื้อหาที่ซับซ้อน\n\n"
                    "แนะนำ:\n"
                    "• ลดขนาดไฟล์ PDF\n"
                    "• แยกเป็นหลายไฟล์เล็กๆ\n"
                    "• ส่งแค่หน้าที่ต้องการแปลง"
                )
            else:
                error_msg += f"รายละเอียด: {str(e)[:200]}"

            await asyncio.to_thread(send_reply, reply_token, error_msg)
        except Exception:
            logger.error("Cannot send error message - reply token might be used")
    except Exception as e:
        logger.error(f"Error processing PDF: {e}", exc_info=True)
        try:
            await asyncio.to_thread(
                send_reply, reply_token,
                f"⚠️ ข้อผิดพลาด\n\nไม่สามารถประมวลผล PDF ได้\n\n{str(e)[:200]}"
            )
        except Exception:
            logger.error("Cannot send error message - reply token might be used")
