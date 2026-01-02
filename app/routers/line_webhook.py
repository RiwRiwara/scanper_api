import logging
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
from linebot.v3.webhooks import MessageEvent, ImageMessageContent
from linebot.v3.exceptions import InvalidSignatureError

from app.config import settings
from app.services.ocr_service import ocr_service

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

            # Perform OCR on the image
            extracted_text = ocr_service.extract_text_from_bytes(image_content)

            # Reply with extracted text
            messaging_api = MessagingApi(api_client)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        TextMessage(
                            text=f"OCR Result:\n\n{extracted_text[:4500]}"
                            if len(extracted_text) > 4500
                            else f"OCR Result:\n\n{extracted_text}"
                        )
                    ],
                )
            )

    except Exception as e:
        logger.error(f"Error processing image: {e}")
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        TextMessage(text=f"Sorry, failed to process image: {str(e)}")
                    ],
                )
            )
