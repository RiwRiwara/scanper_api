import logging
import time
from fastapi import APIRouter, Request, HTTPException, Header
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
)
from linebot.v3.webhooks import (
    MessageEvent,
    ImageMessageContent,
    TextMessageContent,
    FileMessageContent,
)
from linebot.v3.exceptions import InvalidSignatureError

from app.config import settings
from app.services.ocr_service import ocr_service
from app.services.chat_service import chat_service
from app.templates import (
    create_welcome_message,
    create_image_ocr_result,
    create_pdf_ocr_result,
    create_chat_response,
    create_error_message,
)

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

    try:
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

            # Create beautiful Flex Message
            flex_content = create_image_ocr_result(
                extracted_text=extracted_text,
                image_size=content_size,
                processing_time=processing_time,
            )

            # Reply with Flex Message
            messaging_api = MessagingApi(api_client)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        FlexMessage(alt_text="Image OCR Result", contents=flex_content)
                    ],
                )
            )

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            flex_content = create_error_message(
                error_type="Validation Error", error_message=str(e)
            )
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[FlexMessage(alt_text="Error", contents=flex_content)],
                )
            )
    except Exception as e:
        logger.error(f"Error processing image: {e}", exc_info=True)
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            flex_content = create_error_message(
                error_type="Processing Error",
                error_message=f"Failed to process image: {str(e)}",
            )
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[FlexMessage(alt_text="Error", contents=flex_content)],
                )
            )


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event: MessageEvent):
    """Handle text messages from LINE with chatbot."""
    reply_token = event.reply_token
    user_text = event.message.text
    user_id = event.source.user_id  # Get LINE user ID for chat history

    logger.info(f"Received text message from {user_id}: {user_text}")

    try:
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)

            # Get chatbot response with history context
            bot_response = chat_service.chat(user_id=user_id, message=user_text)

            # Create beautiful chat Flex Message
            flex_content = create_chat_response(
                message=bot_response, user_text=user_text
            )

            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        FlexMessage(alt_text="Chat Response", contents=flex_content)
                    ],
                )
            )
    except Exception as e:
        logger.error(f"Error handling text message: {e}", exc_info=True)
        # Fallback to welcome message on error
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            flex_content = create_welcome_message(user_text=user_text)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        FlexMessage(alt_text="Welcome Message", contents=flex_content)
                    ],
                )
            )


@handler.add(MessageEvent, message=FileMessageContent)
def handle_file_message(event: MessageEvent):
    """Handle file messages from LINE (PDF only)."""
    message_id = event.message.id
    reply_token = event.reply_token
    file_name = event.message.file_name
    file_size = event.message.file_size

    logger.info(f"Received file: {file_name}, size={file_size} bytes")

    try:
        # Check if PDF
        if not file_name.lower().endswith(".pdf"):
            with ApiClient(configuration) as api_client:
                messaging_api = MessagingApi(api_client)
                flex_content = create_error_message(
                    error_type="Invalid File Type",
                    error_message="Sorry, I only accept PDF files. Please send a PDF document.",
                )
                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[FlexMessage(alt_text="Error", contents=flex_content)],
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

            # Check size limit (20MB)
            if content_size > 20 * 1024 * 1024:
                raise ValueError("PDF size exceeds 20MB limit")

            if content_size < 100:
                raise ValueError("PDF content too small, might be corrupted")

            logger.info(f"Starting OCR processing for PDF: {file_name} (first 5 pages)")

            # Track processing time
            start_time = time.time()

            # Perform OCR on the PDF (first 5 pages)
            max_pages = 5
            extracted_text = ocr_service.extract_text_from_pdf_bytes(
                file_content, max_pages=max_pages
            )

            processing_time = time.time() - start_time

            logger.info(
                f"OCR completed: text_length={len(extracted_text)}, time={processing_time:.2f}s"
            )

            # Create beautiful Flex Message
            flex_content = create_pdf_ocr_result(
                extracted_text=extracted_text,
                file_name=file_name,
                file_size=content_size,
                pages_processed=min(max_pages, 5),
                max_pages=max_pages,
                processing_time=processing_time,
            )

            # Reply with Flex Message
            messaging_api = MessagingApi(api_client)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        FlexMessage(alt_text="PDF OCR Result", contents=flex_content)
                    ],
                )
            )

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            flex_content = create_error_message(
                error_type="Validation Error", error_message=str(e)
            )
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[FlexMessage(alt_text="Error", contents=flex_content)],
                )
            )
    except Exception as e:
        logger.error(f"Error processing PDF: {e}", exc_info=True)
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            flex_content = create_error_message(
                error_type="Processing Error",
                error_message=f"Failed to process PDF: {str(e)}",
            )
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[FlexMessage(alt_text="Error", contents=flex_content)],
                )
            )
