"""LINE Flex Message templates for OCR results."""

from datetime import datetime
from typing import Optional


def create_welcome_message(user_text: str) -> dict:
    """Create a beautiful welcome message Flex template."""
    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "🤖 OCR Bot",
                            "color": "#ffffff",
                            "size": "xl",
                            "weight": "bold",
                            "flex": 1,
                        }
                    ],
                }
            ],
            "paddingAll": "20px",
            "backgroundColor": "#0066ff",
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "Hello! I'm your OCR assistant 👋",
                    "weight": "bold",
                    "size": "lg",
                    "margin": "md",
                    "wrap": True,
                },
                {
                    "type": "separator",
                    "margin": "lg",
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "lg",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": "📸",
                                    "size": "xl",
                                    "flex": 0,
                                },
                                {
                                    "type": "text",
                                    "text": "Send Image",
                                    "weight": "bold",
                                    "margin": "md",
                                    "flex": 2,
                                },
                            ],
                        },
                        {
                            "type": "text",
                            "text": "I'll extract all text from your image",
                            "size": "sm",
                            "color": "#aaaaaa",
                            "wrap": True,
                            "margin": "sm",
                        },
                        {
                            "type": "separator",
                            "margin": "md",
                        },
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": "📄",
                                    "size": "xl",
                                    "flex": 0,
                                },
                                {
                                    "type": "text",
                                    "text": "Send PDF",
                                    "weight": "bold",
                                    "margin": "md",
                                    "flex": 2,
                                },
                            ],
                            "margin": "md",
                        },
                        {
                            "type": "text",
                            "text": "I'll extract text from first 10 pages",
                            "size": "sm",
                            "color": "#aaaaaa",
                            "wrap": True,
                            "margin": "sm",
                        },
                    ],
                },
                {
                    "type": "separator",
                    "margin": "lg",
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "lg",
                    "contents": [
                        {
                            "type": "text",
                            "text": "You said:",
                            "size": "xs",
                            "color": "#aaaaaa",
                        },
                        {
                            "type": "text",
                            "text": user_text,
                            "size": "sm",
                            "wrap": True,
                            "margin": "xs",
                            "color": "#666666",
                        },
                    ],
                },
            ],
            "paddingAll": "20px",
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "Powered by Azure Document Intelligence",
                    "size": "xxs",
                    "color": "#aaaaaa",
                    "align": "center",
                }
            ],
            "paddingAll": "10px",
        },
    }


def create_image_ocr_result(
    extracted_text: str, image_size: int, processing_time: Optional[float] = None
) -> dict:
    """Create a beautiful image OCR result Flex template."""
    # Calculate display size
    size_kb = image_size / 1024
    size_mb = size_kb / 1024

    if size_mb >= 1:
        size_display = f"{size_mb:.2f} MB"
    else:
        size_display = f"{size_kb:.2f} KB"

    # Truncate text if too long
    display_text = extracted_text[:3000] if len(extracted_text) > 3000 else extracted_text
    is_truncated = len(extracted_text) > 3000

    footer_contents = [
        {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": "📏 Size:",
                    "size": "xs",
                    "color": "#aaaaaa",
                    "flex": 0,
                },
                {
                    "type": "text",
                    "text": size_display,
                    "size": "xs",
                    "color": "#666666",
                    "align": "end",
                },
            ],
        },
        {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": "📝 Length:",
                    "size": "xs",
                    "color": "#aaaaaa",
                    "flex": 0,
                },
                {
                    "type": "text",
                    "text": f"{len(extracted_text)} chars",
                    "size": "xs",
                    "color": "#666666",
                    "align": "end",
                },
            ],
            "margin": "xs",
        },
    ]

    if processing_time:
        footer_contents.append(
            {
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {
                        "type": "text",
                        "text": "⏱️ Time:",
                        "size": "xs",
                        "color": "#aaaaaa",
                        "flex": 0,
                    },
                    {
                        "type": "text",
                        "text": f"{processing_time:.2f}s",
                        "size": "xs",
                        "color": "#666666",
                        "align": "end",
                    },
                ],
                "margin": "xs",
            }
        )

    if is_truncated:
        footer_contents.append(
            {
                "type": "separator",
                "margin": "md",
            }
        )
        footer_contents.append(
            {
                "type": "text",
                "text": "⚠️ Text truncated to 3000 chars",
                "size": "xxs",
                "color": "#ff6b6b",
                "align": "center",
                "margin": "sm",
            }
        )

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "📸",
                            "size": "xl",
                            "flex": 0,
                        },
                        {
                            "type": "text",
                            "text": "Image OCR Result",
                            "color": "#ffffff",
                            "size": "lg",
                            "weight": "bold",
                            "margin": "md",
                            "flex": 1,
                        },
                    ],
                }
            ],
            "paddingAll": "20px",
            "backgroundColor": "#17c964",
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "Extracted Text:",
                    "weight": "bold",
                    "size": "md",
                    "color": "#111111",
                },
                {
                    "type": "separator",
                    "margin": "md",
                },
                {
                    "type": "text",
                    "text": display_text if display_text else "No text found in image.",
                    "size": "sm",
                    "wrap": True,
                    "margin": "md",
                    "color": "#333333",
                },
            ],
            "paddingAll": "20px",
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": footer_contents,
            "paddingAll": "15px",
            "backgroundColor": "#f5f5f5",
        },
    }


def create_pdf_ocr_result(
    extracted_text: str,
    file_name: str,
    file_size: int,
    pages_processed: int,
    max_pages: int,
    processing_time: Optional[float] = None,
) -> dict:
    """Create a beautiful PDF OCR result Flex template."""
    # Calculate display size
    size_kb = file_size / 1024
    size_mb = size_kb / 1024

    if size_mb >= 1:
        size_display = f"{size_mb:.2f} MB"
    else:
        size_display = f"{size_kb:.2f} KB"

    # Truncate text if too long
    display_text = extracted_text[:3000] if len(extracted_text) > 3000 else extracted_text
    is_truncated = len(extracted_text) > 3000

    footer_contents = [
        {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": "📄 Pages:",
                    "size": "xs",
                    "color": "#aaaaaa",
                    "flex": 0,
                },
                {
                    "type": "text",
                    "text": f"{pages_processed} หน้า (จากทั้งหมด {max_pages} หน้าแรก)",
                    "size": "xs",
                    "color": "#666666",
                    "align": "end",
                },
            ],
        },
        {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": "📏 Size:",
                    "size": "xs",
                    "color": "#aaaaaa",
                    "flex": 0,
                },
                {
                    "type": "text",
                    "text": size_display,
                    "size": "xs",
                    "color": "#666666",
                    "align": "end",
                },
            ],
            "margin": "xs",
        },
        {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": "📝 Length:",
                    "size": "xs",
                    "color": "#aaaaaa",
                    "flex": 0,
                },
                {
                    "type": "text",
                    "text": f"{len(extracted_text)} chars",
                    "size": "xs",
                    "color": "#666666",
                    "align": "end",
                },
            ],
            "margin": "xs",
        },
    ]

    if processing_time:
        footer_contents.append(
            {
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {
                        "type": "text",
                        "text": "⏱️ Time:",
                        "size": "xs",
                        "color": "#aaaaaa",
                        "flex": 0,
                    },
                    {
                        "type": "text",
                        "text": f"{processing_time:.2f}s",
                        "size": "xs",
                        "color": "#666666",
                        "align": "end",
                    },
                ],
                "margin": "xs",
            }
        )

    if is_truncated:
        footer_contents.append(
            {
                "type": "separator",
                "margin": "md",
            }
        )
        footer_contents.append(
            {
                "type": "text",
                "text": "⚠️ Text truncated to 3000 chars",
                "size": "xxs",
                "color": "#ff6b6b",
                "align": "center",
                "margin": "sm",
            }
        )

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "📄",
                            "size": "xl",
                            "flex": 0,
                        },
                        {
                            "type": "text",
                            "text": "PDF OCR Result",
                            "color": "#ffffff",
                            "size": "lg",
                            "weight": "bold",
                            "margin": "md",
                            "flex": 1,
                        },
                    ],
                }
            ],
            "paddingAll": "20px",
            "backgroundColor": "#f5a524",
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "📎 File Name:",
                            "size": "xs",
                            "color": "#aaaaaa",
                        },
                        {
                            "type": "text",
                            "text": file_name,
                            "size": "sm",
                            "weight": "bold",
                            "wrap": True,
                            "margin": "xs",
                        },
                    ],
                },
                {
                    "type": "separator",
                    "margin": "md",
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "📖",
                            "size": "md",
                            "flex": 0,
                        },
                        {
                            "type": "text",
                            "text": f"แสดง {pages_processed} หน้า (แยกตามหน้า)",
                            "weight": "bold",
                            "size": "sm",
                            "color": "#17c964",
                            "margin": "sm",
                            "flex": 1,
                        },
                    ],
                    "margin": "md",
                },
                {
                    "type": "separator",
                    "margin": "md",
                },
                {
                    "type": "text",
                    "text": display_text if display_text else "No text found in PDF.",
                    "size": "sm",
                    "wrap": True,
                    "margin": "md",
                    "color": "#333333",
                },
            ],
            "paddingAll": "20px",
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": footer_contents,
            "paddingAll": "15px",
            "backgroundColor": "#f5f5f5",
        },
    }


def create_chat_response(message: str, user_text: str) -> dict:
    """Create a beautiful chat response Flex template."""
    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "💬",
                            "size": "xl",
                            "flex": 0,
                        },
                        {
                            "type": "text",
                            "text": "OCR Assistant",
                            "color": "#ffffff",
                            "size": "lg",
                            "weight": "bold",
                            "margin": "md",
                            "flex": 1,
                        },
                    ],
                }
            ],
            "paddingAll": "20px",
            "backgroundColor": "#9333ea",
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "คุณถาม:",
                            "size": "xs",
                            "color": "#aaaaaa",
                        },
                        {
                            "type": "text",
                            "text": user_text,
                            "size": "sm",
                            "wrap": True,
                            "margin": "xs",
                            "color": "#666666",
                            "weight": "bold",
                        },
                    ],
                },
                {
                    "type": "separator",
                    "margin": "lg",
                },
                {
                    "type": "text",
                    "text": message,
                    "size": "sm",
                    "wrap": True,
                    "margin": "lg",
                    "color": "#333333",
                },
            ],
            "paddingAll": "20px",
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "📸",
                            "size": "sm",
                            "flex": 0,
                        },
                        {
                            "type": "text",
                            "text": "ส่งรูปภาพมาแปลงข้อความได้เลย",
                            "size": "xs",
                            "color": "#aaaaaa",
                            "margin": "sm",
                            "flex": 1,
                        },
                    ],
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "📄",
                            "size": "sm",
                            "flex": 0,
                        },
                        {
                            "type": "text",
                            "text": "ส่ง PDF มาแปลง 10 หน้าแรกได้",
                            "size": "xs",
                            "color": "#aaaaaa",
                            "margin": "sm",
                            "flex": 1,
                        },
                    ],
                    "margin": "xs",
                },
            ],
            "paddingAll": "15px",
            "backgroundColor": "#f5f5f5",
        },
    }


def create_error_message(error_type: str, error_message: str) -> dict:
    """Create a beautiful error message Flex template."""
    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "⚠️",
                            "size": "xl",
                            "flex": 0,
                        },
                        {
                            "type": "text",
                            "text": error_type,
                            "color": "#ffffff",
                            "size": "lg",
                            "weight": "bold",
                            "margin": "md",
                            "flex": 1,
                        },
                    ],
                }
            ],
            "paddingAll": "20px",
            "backgroundColor": "#ff6b6b",
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": error_message,
                    "size": "sm",
                    "wrap": True,
                    "color": "#666666",
                }
            ],
            "paddingAll": "20px",
        },
    }
