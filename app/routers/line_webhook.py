import logging
import time
import json
import asyncio
from fastapi import APIRouter, Request, HTTPException, Header
from linebot.v3 import WebhookHandler
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/line", tags=["LINE"])

# LINE SDK setup
configuration = Configuration(access_token=settings.LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(settings.LINE_CHANNEL_SECRET)


@router.post("/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: str = Header(..., alias="X-Line-Signature"),
):
    """LINE Webhook endpoint to receive messages."""
    body = await request.body()
    body_str = body.decode("utf-8")

    try:
        handler.handle(body_str, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    return {"status": "ok"}


@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event: MessageEvent):
    """Handle image messages from LINE and perform OCR."""
    message_id = event.message.id
    reply_token = event.reply_token
    line_user_id = event.source.user_id

    async def process_image():
        try:
            # Get or create user in database
            user = await user_repository.get_or_create_user(line_user_id)
            await user_repository.increment_message_count(user)

            # Get image content from LINE
            with ApiClient(configuration) as api_client:
                blob_api = MessagingApiBlob(api_client)
                image_content = blob_api.get_message_content(message_id)

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

                # Perform OCR on the image
                extracted_text = ocr_service.extract_text_from_bytes(image_content)

                processing_time = time.time() - start_time

                logger.info(
                    f"OCR completed: message_id={message_id}, text_length={len(extracted_text)}, time={processing_time:.2f}s"
                )

                # Format as simple text message (more reliable than Flex Message)
                size_kb = content_size / 1024
                size_mb = size_kb / 1024
                size_display = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{size_kb:.2f} KB"

                # Truncate if too long
                display_text = extracted_text[:2000] if len(extracted_text) > 2000 else extracted_text
                truncated_notice = "\n\n⚠️ (แสดงเฉพาะ 2000 ตัวอักษรแรก)" if len(extracted_text) > 2000 else ""

                result_text = (
                    f"📸 IMAGE OCR RESULT\n"
                    f"{'='*30}\n\n"
                    f"{display_text if display_text.strip() else 'ไม่พบข้อความในรูปภาพ'}\n"
                    f"{truncated_notice}\n\n"
                    f"{'='*30}\n"
                    f"📏 Size: {size_display}\n"
                    f"📝 Length: {len(extracted_text)} characters\n"
                    f"⏱️ Processing: {processing_time:.2f}s"
                )

                # Save message to database
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

                # Reply with simple text message
                messaging_api = MessagingApi(api_client)
                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text=result_text)],
                    )
                )

        except ValueError as e:
            logger.warning(f"Validation error: {e}")
            with ApiClient(configuration) as api_client:
                messaging_api = MessagingApi(api_client)
                error_text = f"⚠️ VALIDATION ERROR\n\n{str(e)}"
                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text=error_text)],
                    )
                )
        except Exception as e:
            logger.error(f"Error processing image: {e}", exc_info=True)
            try:
                with ApiClient(configuration) as api_client:
                    messaging_api = MessagingApi(api_client)
                    error_text = f"⚠️ ERROR\n\nFailed to process image: {str(e)[:300]}"
                    messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[TextMessage(text=error_text)],
                        )
                    )
            except Exception:
                # Reply token might already be used, just log
                logger.error("Cannot send error message - reply token might be used")

    # Run the async function synchronously
    asyncio.run(process_image())


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event: MessageEvent):
    """Handle text messages from LINE with chatbot."""
    reply_token = event.reply_token
    user_text = event.message.text
    line_user_id = event.source.user_id  # Get LINE user ID for chat history

    logger.info(f"Received text message from {line_user_id}: {user_text}")

    async def process_text():
        try:
            # Get or create user in database
            user = await user_repository.get_or_create_user(line_user_id)
            await user_repository.increment_message_count(user)

            with ApiClient(configuration) as api_client:
                messaging_api = MessagingApi(api_client)

                # Get chatbot response with database history
                bot_response = await chat_service.chat(user=user, message=user_text)

                # Validate bot response
                if not bot_response or not bot_response.strip():
                    logger.warning("Empty bot response, using fallback")
                    bot_response = (
                        "สวัสดีครับ! ผมเป็น OCR Assistant 📄\n\n"
                        "ส่งรูปภาพหรือไฟล์ PDF มาให้ผมช่วยแปลงเป็นข้อความได้เลยนะครับ!"
                    )

                logger.info(f"Bot response length: {len(bot_response)}")

                # Format response message
                response_text = f"💬 OCR Assistant\n\n{bot_response}\n\n───────────────\n📸 ส่งรูปภาพมาแปลงข้อความได้เลย\n📄 ส่ง PDF มาแปลง 10 หน้าแรกได้"

                # Send simple text message (more reliable than Flex Message)
                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text=response_text)],
                    )
                )
        except LineApiException as e:
            # LINE API error - reply token might be invalid or already used
            logger.error(f"LINE API error in text handler: {e}", exc_info=True)
            # Cannot reply again with same token, just log the error
        except Exception as e:
            logger.error(f"Error handling text message: {e}", exc_info=True)
            # Try fallback message only if we haven't sent anything yet
            try:
                with ApiClient(configuration) as api_client:
                    messaging_api = MessagingApi(api_client)
                    fallback_text = (
                        "💬 OCR Assistant\n\n"
                        "สวัสดีครับ! ผมเป็น OCR Assistant ที่ช่วยแปลงเอกสารเป็นข้อความ\n\n"
                        "📸 ส่งรูปภาพมาแปลงข้อความได้เลย\n"
                        "📄 ส่ง PDF มาแปลง 10 หน้าแรกได้"
                    )
                    messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[TextMessage(text=fallback_text)],
                        )
                    )
            except LineApiException:
                # Reply token already used, just log
                logger.error("Cannot send fallback message - reply token already used")

    # Run the async function synchronously
    asyncio.run(process_text())


@handler.add(MessageEvent, message=FileMessageContent)
def handle_file_message(event: MessageEvent):
    """Handle file messages from LINE (PDF only)."""
    message_id = event.message.id
    reply_token = event.reply_token
    file_name = event.message.file_name
    file_size = event.message.file_size
    line_user_id = event.source.user_id

    logger.info(f"Received file from {line_user_id}: {file_name}, size={file_size} bytes")

    async def process_pdf():
        try:
            # Get or create user in database
            user = await user_repository.get_or_create_user(line_user_id)
            await user_repository.increment_message_count(user)

            # Check if PDF
            if not file_name.lower().endswith(".pdf"):
                with ApiClient(configuration) as api_client:
                    messaging_api = MessagingApi(api_client)
                    error_text = (
                        "⚠️ INVALID FILE TYPE\n\n"
                        "Sorry, I only accept PDF files.\n"
                        "Please send a PDF document."
                    )
                    messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[TextMessage(text=error_text)],
                        )
                    )
                return

            # Get file content from LINE
            with ApiClient(configuration) as api_client:
                blob_api = MessagingApiBlob(api_client)
                file_content = blob_api.get_message_content(message_id)

                # Validate file content
                if not file_content:
                    raise ValueError("Empty file content received")

                content_size = len(file_content)
                logger.info(f"PDF file size: {content_size} bytes")

                # Check size limit (increased to 100MB since we extract first 10 pages only)
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

                # Perform OCR on the PDF (first 10 pages)
                max_pages = 10
                extracted_text = ocr_service.extract_text_from_pdf_bytes(
                    file_content, max_pages=max_pages
                )

                processing_time = time.time() - start_time

                # Count actual pages processed by counting page headers
                pages_processed = extracted_text.count("━━━━━ หน้า")

                logger.info(
                    f"OCR completed: pages={pages_processed}, text_length={len(extracted_text)}, time={processing_time:.2f}s"
                )

                # Format as simple text message (more reliable than Flex Message)
                size_kb = content_size / 1024
                size_mb = size_kb / 1024
                size_display = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{size_kb:.2f} KB"

                # Truncate if too long
                display_text = extracted_text[:2000] if len(extracted_text) > 2000 else extracted_text
                truncated_notice = "\n\n⚠️ (แสดงเฉพาะ 2000 ตัวอักษรแรก)" if len(extracted_text) > 2000 else ""

                result_text = (
                    f"📄 PDF OCR RESULT\n"
                    f"{'='*30}\n"
                    f"📎 File: {file_name}\n"
                    f"📖 Pages: {pages_processed} หน้า (จาก {max_pages} หน้าแรก)\n"
                    f"{'='*30}\n\n"
                    f"{display_text if display_text.strip() else 'ไม่พบข้อความใน PDF'}\n"
                    f"{truncated_notice}\n\n"
                    f"{'='*30}\n"
                    f"📏 Size: {size_display}\n"
                    f"📝 Length: {len(extracted_text)} characters\n"
                    f"⏱️ Processing: {processing_time:.2f}s"
                )

                # Save message to database
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

                # Reply with simple text message
                messaging_api = MessagingApi(api_client)
                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text=result_text)],
                    )
                )

        except ValueError as e:
            logger.warning(f"Validation error: {e}")
            try:
                with ApiClient(configuration) as api_client:
                    messaging_api = MessagingApi(api_client)
                    error_text = f"⚠️ ข้อผิดพลาดในการตรวจสอบ\n\n{str(e)}"
                    messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[TextMessage(text=error_text)],
                        )
                    )
            except Exception:
                logger.error("Cannot send error message - reply token might be used")
        except HttpResponseError as e:
            logger.error(f"Azure API error: {e}", exc_info=True)
            try:
                # Handle Azure-specific errors
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

                with ApiClient(configuration) as api_client:
                    messaging_api = MessagingApi(api_client)
                    messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[TextMessage(text=error_msg)],
                        )
                    )
            except Exception:
                logger.error("Cannot send error message - reply token might be used")
        except Exception as e:
            logger.error(f"Error processing PDF: {e}", exc_info=True)
            try:
                with ApiClient(configuration) as api_client:
                    messaging_api = MessagingApi(api_client)
                    error_text = f"⚠️ ข้อผิดพลาด\n\nไม่สามารถประมวลผล PDF ได้\n\n{str(e)[:200]}"
                    messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[TextMessage(text=error_text)],
                        )
                    )
            except Exception:
                logger.error("Cannot send error message - reply token might be used")

    # Run the async function synchronously
    asyncio.run(process_pdf())
