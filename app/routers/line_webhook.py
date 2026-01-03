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
    FlexMessage,
    FlexContainer,
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


# Preview length for Flex Message (show first N characters)
PREVIEW_LENGTH = 500


def build_ocr_flex_message(
    title: str,
    preview_text: str,
    full_text_length: int,
    message_id: str,
    metadata: dict,
    quota_info: str,
) -> dict:
    """
    Build a compact Flex Message with preview and "ดูเพิ่มเติม" button.

    Args:
        title: Message title (e.g., "📸 IMAGE OCR")
        preview_text: First ~500 chars of OCR result
        full_text_length: Total length of OCR text
        message_id: Database message ID for LIFF URL
        metadata: Dict with size, processing_time, etc.
        quota_info: User quota string

    Returns:
        Flex Message JSON dict
    """
    # Truncate preview if needed
    if len(preview_text) > PREVIEW_LENGTH:
        preview_text = preview_text[:PREVIEW_LENGTH] + "..."

    # Build LIFF URL
    liff_url = f"{settings.LIFF_URL}/ocr/{message_id}"

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": title,
                    "weight": "bold",
                    "size": "lg",
                    "color": "#1DB446"
                }
            ],
            "backgroundColor": "#F5F5F5",
            "paddingAll": "15px"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": preview_text if preview_text.strip() else "ไม่พบข้อความ",
                    "wrap": True,
                    "size": "sm",
                    "color": "#333333",
                    "maxLines": 10
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "lg",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {"type": "text", "text": "📝 ความยาว", "size": "xs", "color": "#888888", "flex": 1},
                                {"type": "text", "text": f"{full_text_length:,} ตัวอักษร", "size": "xs", "color": "#333333", "flex": 2, "align": "end"}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "margin": "sm",
                            "contents": [
                                {"type": "text", "text": "📏 ขนาด", "size": "xs", "color": "#888888", "flex": 1},
                                {"type": "text", "text": metadata.get("size_display", "-"), "size": "xs", "color": "#333333", "flex": 2, "align": "end"}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "margin": "sm",
                            "contents": [
                                {"type": "text", "text": "⏱️ เวลา", "size": "xs", "color": "#888888", "flex": 1},
                                {"type": "text", "text": f"{metadata.get('processing_time', 0):.2f}s", "size": "xs", "color": "#333333", "flex": 2, "align": "end"}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "margin": "sm",
                            "contents": [
                                {"type": "text", "text": "📊 โควต้า", "size": "xs", "color": "#888888", "flex": 1},
                                {"type": "text", "text": quota_info, "size": "xs", "color": "#1DB446", "flex": 2, "align": "end"}
                            ]
                        }
                    ]
                }
            ],
            "paddingAll": "15px"
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "action": {
                        "type": "uri",
                        "label": f"📖 ดูข้อความทั้งหมด ({full_text_length:,} ตัวอักษร)",
                        "uri": liff_url
                    },
                    "style": "primary",
                    "color": "#1DB446",
                    "height": "sm"
                }
            ],
            "paddingAll": "15px"
        }
    }


def send_flex_reply(reply_token: str, alt_text: str, flex_content: dict):
    """Send a Flex Message reply."""
    try:
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        FlexMessage(
                            alt_text=alt_text,
                            contents=FlexContainer.from_dict(flex_content)
                        )
                    ],
                )
            )
    except LineApiException as e:
        logger.error(f"Failed to send flex reply: {e}")


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

        # Check OCR limit
        ocr_allowed, ocr_remaining, ocr_limit = await user_repository.check_ocr_limit(user)
        if not ocr_allowed:
            logger.warning(f"OCR limit reached for user {line_user_id}: {user.ocr_count_session}/{ocr_limit}")
            send_reply(
                reply_token,
                f"⚠️ OCR LIMIT REACHED\n\n"
                f"คุณใช้โควต้า OCR หมดแล้ว\n"
                f"ใช้ไปแล้ว: {user.ocr_count_session}/{ocr_limit} หน้า\n\n"
                f"กรุณาติดต่อแอดมินเพื่อเพิ่มโควต้า\n"
                f"หรือรอให้แอดมินรีเซ็ตโควต้าให้"
            )
            return

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

        # Save message to database (async) - get message for ID
        saved_message = await message_repository.create_message(
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

        # Increment OCR count (1 page for image)
        session_count, remaining = await user_repository.increment_ocr_count(user, pages=1)
        quota_info = f"{session_count}/{user.ocr_limit} (เหลือ {remaining})"

        # Build and send Flex Message with preview
        if not extracted_text.strip():
            # No text found - simple text message
            result_text = (
                f"📸 IMAGE OCR RESULT\n"
                f"{'='*30}\n\n"
                f"ไม่พบข้อความในรูปภาพ\n\n"
                f"{'='*30}\n"
                f"📏 Size: {size_display}\n"
                f"⏱️ Processing: {processing_time:.2f}s\n"
                f"📊 โควต้า: {quota_info}"
            )
            await asyncio.to_thread(send_reply, reply_token, result_text)
        else:
            # Build Flex Message with preview and "ดูเพิ่มเติม" button
            flex_content = build_ocr_flex_message(
                title="📸 IMAGE OCR",
                preview_text=extracted_text,
                full_text_length=len(extracted_text),
                message_id=str(saved_message.id),
                metadata={
                    "size_display": size_display,
                    "processing_time": processing_time,
                },
                quota_info=quota_info,
            )

            # Send Flex Message
            await asyncio.to_thread(
                send_flex_reply,
                reply_token,
                f"OCR Result: {len(extracted_text)} ตัวอักษร",
                flex_content
            )

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
    """Process text message - show user info and instructions (no LLM)."""
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

        # Build response with user quota info
        quota_used = user.ocr_count_session
        quota_limit = user.ocr_limit
        quota_remaining = user.ocr_remaining
        total_ocr = user.ocr_count_total

        response_text = (
            f"📄 Scanper OCR Assistant\n"
            f"{'='*30}\n\n"
            f"สวัสดีค่ะ! ส่งรูปภาพหรือ PDF มาให้ช่วยแปลงเป็นข้อความได้เลยนะคะ\n\n"
            f"📊 โควต้าของคุณ\n"
            f"├─ ใช้ไปแล้ว: {quota_used}/{quota_limit} หน้า\n"
            f"├─ เหลือ: {quota_remaining} หน้า\n"
            f"└─ รวมทั้งหมด: {total_ocr} หน้า\n\n"
            f"{'─'*30}\n"
            f"📸 ส่งรูปภาพ → แปลงข้อความ (1 หน้า)\n"
            f"📄 ส่ง PDF → แปลง 10 หน้าแรก\n"
            f"{'─'*30}\n\n"
            f"💡 หากโควต้าหมด กรุณาติดต่อแอดมิน"
        )

        # Send reply
        await asyncio.to_thread(send_reply, reply_token, response_text)

    except LineApiException as e:
        logger.error(f"LINE API error in text handler: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Error handling text message: {e}", exc_info=True)
        try:
            fallback_text = (
                "📄 Scanper OCR Assistant\n\n"
                "สวัสดีค่ะ! ส่งรูปภาพหรือ PDF มาให้ช่วยแปลงเป็นข้อความได้เลยนะคะ\n\n"
                "📸 ส่งรูปภาพ → แปลงข้อความ\n"
                "📄 ส่ง PDF → แปลง 10 หน้าแรก"
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

        # Check OCR limit (PDF counts as 10 pages max)
        ocr_allowed, ocr_remaining, ocr_limit = await user_repository.check_ocr_limit(user)
        if not ocr_allowed:
            logger.warning(f"OCR limit reached for user {line_user_id}: {user.ocr_count_session}/{ocr_limit}")
            send_reply(
                reply_token,
                f"⚠️ OCR LIMIT REACHED\n\n"
                f"คุณใช้โควต้า OCR หมดแล้ว\n"
                f"ใช้ไปแล้ว: {user.ocr_count_session}/{ocr_limit} หน้า\n\n"
                f"กรุณาติดต่อแอดมินเพื่อเพิ่มโควต้า\n"
                f"หรือรอให้แอดมินรีเซ็ตโควต้าให้"
            )
            return

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

        # Save message to database (async) - get message for ID
        saved_message = await message_repository.create_message(
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

        # Increment OCR count by pages processed (minimum 1)
        pages_to_count = max(1, pages_processed)
        session_count, remaining = await user_repository.increment_ocr_count(user, pages=pages_to_count)
        quota_info = f"{session_count}/{user.ocr_limit} (เหลือ {remaining})"

        # Build and send Flex Message with preview
        if not extracted_text.strip():
            # No text found - simple text message
            result_text = (
                f"📄 PDF OCR RESULT\n"
                f"{'='*30}\n"
                f"📎 File: {file_name}\n"
                f"📖 Pages: {pages_processed} หน้า\n"
                f"{'='*30}\n\n"
                f"ไม่พบข้อความใน PDF\n\n"
                f"{'='*30}\n"
                f"📏 Size: {size_display}\n"
                f"⏱️ Processing: {processing_time:.2f}s\n"
                f"📊 โควต้า: {quota_info}"
            )
            await asyncio.to_thread(send_reply, reply_token, result_text)
        else:
            # Build Flex Message with preview and "ดูเพิ่มเติม" button
            flex_content = build_ocr_flex_message(
                title=f"📄 PDF OCR ({pages_processed} หน้า)",
                preview_text=extracted_text,
                full_text_length=len(extracted_text),
                message_id=str(saved_message.id),
                metadata={
                    "size_display": size_display,
                    "processing_time": processing_time,
                    "file_name": file_name,
                    "pages": pages_processed,
                },
                quota_info=quota_info,
            )

            # Send Flex Message
            await asyncio.to_thread(
                send_flex_reply,
                reply_token,
                f"PDF OCR: {file_name} - {len(extracted_text)} ตัวอักษร",
                flex_content
            )

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
