"""Chat service using OpenAI with database-backed history support."""

import logging
from typing import List, Dict
from openai import OpenAI

from app.config import settings
from app.models.user import User
from app.models.message import Message, MessageType
from app.repositories.message_repository import message_repository

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "gpt-4o-mini"  # Cheap and fast model
        self.max_history_length = 20  # Keep last 20 messages per user

        # System prompt that always recommends OCR
        self.system_prompt = """คุณเป็น OCR Assistant Bot ที่ช่วยผู้ใช้งานในการแปลงเอกสารเป็นข้อความ

**ภารกิจหลัก:**
- แนะนำผู้ใช้ให้ใช้ฟีเจอร์ OCR (แปลงรูปภาพและ PDF เป็นข้อความ)
- ตอบคำถามเกี่ยวกับการใช้งาน OCR
- แนะนำวิธีส่งเอกสารที่ดีที่สุดเพื่อให้ได้ผลลัพธ์ที่ดี

**ความสามารถของบอท:**
1. 📸 แปลงรูปภาพเป็นข้อความ (รองรับทุกภาษา)
2. 📄 แปลงไฟล์ PDF เป็นข้อความ (10 หน้าแรก)
3. ใช้ Azure Document Intelligence - เทคโนโลยี OCR ที่ทันสมัย

**คำแนะนำเมื่อตอบ:**
- พูดจาเป็นกันเอง แต่มืออาชีพ
- แนะนำให้ผู้ใช้ส่งรูปภาพหรือ PDF มาใช้งาน OCR เสมอ
- หากผู้ใช้ถามคำถามทั่วไป ให้ตอบสั้นๆ แล้วหันกลับมาแนะนำ OCR
- ใช้อิโมจิประกอบเพื่อให้น่าสนใจ แต่ไม่มากเกินไป

ตัวอย่าง:
- ถ้าผู้ใช้ถาม "สวัสดี" -> ตอบทักทายและแนะนำว่าสามารถส่งรูปภาพมาแปลงข้อความได้
- ถ้าผู้ใช้ถาม "มีอะไรช่วยได้บ้าง" -> อธิบายความสามารถ OCR
- ถ้าผู้ใช้ถามอย่างอื่น -> ตอบคำถามสั้นๆ แล้วแนะนำ OCR

จำไว้ว่า: เป้าหมายคือให้ผู้ใช้ส่งเอกสารมาใช้งาน OCR!"""

    async def get_chat_history(self, user: User) -> List[Dict[str, str]]:
        """
        Get chat history from database for a user.

        Args:
            user: User document

        Returns:
            List of message dicts with 'role' and 'content'
        """
        try:
            # Get text messages from database
            messages = await message_repository.get_text_messages_for_chat(
                user=user, limit=self.max_history_length
            )

            # Convert to OpenAI format
            history = []
            for msg in messages:
                # Get role from metadata (default to 'user' if not found)
                role = msg.metadata.get("role", "user")
                history.append({"role": role, "content": msg.content})

            return history

        except Exception as e:
            logger.error(f"Error loading chat history: {e}", exc_info=True)
            return []

    async def chat(self, user: User, message: str) -> str:
        """
        Chat with the bot using OpenAI with database-backed history.

        Args:
            user: User document
            message: User's message

        Returns:
            Bot's response
        """
        try:
            # Get user's chat history from database
            history = await self.get_chat_history(user)

            # Save user message to database
            await message_repository.create_message(
                user=user,
                message_type=MessageType.TEXT,
                content=message,
                metadata={"role": "user"},
            )

            # Prepare messages for OpenAI
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(history)
            messages.append({"role": "user", "content": message})

            logger.info(
                f"Sending chat request: user={user.line_user_id}, history_length={len(history)}"
            )

            # Call OpenAI
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=500,  # Limit response length to save costs
                temperature=0.7,  # Some creativity but not too much
            )

            assistant_message = response.choices[0].message.content

            # Save assistant response to database
            await message_repository.create_message(
                user=user,
                message_type=MessageType.TEXT,
                content=assistant_message,
                metadata={"role": "assistant", "tokens_used": response.usage.total_tokens},
            )

            logger.info(f"Chat response saved: tokens={response.usage.total_tokens}")

            return assistant_message

        except Exception as e:
            logger.error(f"Error in chat service: {e}", exc_info=True)
            return "ขอโทษครับ เกิดข้อผิดพลาดในการตอบกลับ 😅\n\nแต่คุณสามารถส่งรูปภาพหรือไฟล์ PDF มาให้ผมช่วยแปลงเป็นข้อความได้เลยนะครับ! 📸📄"


chat_service = ChatService()
