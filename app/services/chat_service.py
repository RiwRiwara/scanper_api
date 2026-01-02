"""Chat service using OpenAI with history support."""

import logging
from typing import Dict, List
from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "gpt-4o-mini"  # Cheap and fast model
        # Store chat history per user: {user_id: [messages]}
        self.chat_history: Dict[str, List[Dict[str, str]]] = {}
        self.max_history_length = 20  # Keep last 20 messages per user

        # System prompt that always recommends OCR
        self.system_prompt = """คุณเป็น OCR Assistant Bot ที่ช่วยผู้ใช้งานในการแปลงเอกสารเป็นข้อความ

**ภารกิจหลัก:**
- แนะนำผู้ใช้ให้ใช้ฟีเจอร์ OCR (แปลงรูปภาพและ PDF เป็นข้อความ)
- ตอบคำถามเกี่ยวกับการใช้งาน OCR
- แนะนำวิธีส่งเอกสารที่ดีที่สุดเพื่อให้ได้ผลลัพธ์ที่ดี

**ความสามารถของบอท:**
1. 📸 แปลงรูปภาพเป็นข้อความ (รองรับทุกภาษา)
2. 📄 แปลงไฟล์ PDF เป็นข้อความ (5 หน้าแรก)
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

    def get_chat_history(self, user_id: str) -> List[Dict[str, str]]:
        """Get chat history for a user."""
        if user_id not in self.chat_history:
            self.chat_history[user_id] = []
        return self.chat_history[user_id]

    def add_to_history(self, user_id: str, role: str, content: str):
        """Add a message to chat history."""
        history = self.get_chat_history(user_id)
        history.append({"role": role, "content": content})

        # Trim history if too long (keep system prompt + last N messages)
        if len(history) > self.max_history_length:
            self.chat_history[user_id] = history[-self.max_history_length :]

    def clear_history(self, user_id: str):
        """Clear chat history for a user."""
        if user_id in self.chat_history:
            del self.chat_history[user_id]

    def chat(self, user_id: str, message: str) -> str:
        """
        Chat with the bot using OpenAI.

        Args:
            user_id: LINE user ID for maintaining chat history
            message: User's message

        Returns:
            Bot's response
        """
        try:
            # Get user's chat history
            history = self.get_chat_history(user_id)

            # Add user message to history
            self.add_to_history(user_id, "user", message)

            # Prepare messages for OpenAI
            messages = [{"role": "system", "content": self.system_prompt}]

            # Add chat history (excluding the message we just added)
            messages.extend(history[:-1])

            # Add current user message
            messages.append({"role": "user", "content": message})

            logger.info(
                f"Sending chat request: user_id={user_id}, history_length={len(history)}"
            )

            # Call OpenAI
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=500,  # Limit response length to save costs
                temperature=0.7,  # Some creativity but not too much
            )

            assistant_message = response.choices[0].message.content

            # Add assistant response to history
            self.add_to_history(user_id, "assistant", assistant_message)

            logger.info(
                f"Chat response received: tokens_used={response.usage.total_tokens}"
            )

            return assistant_message

        except Exception as e:
            logger.error(f"Error in chat service: {e}", exc_info=True)
            return "ขอโทษครับ เกิดข้อผิดพลาดในการตอบกลับ 😅\n\nแต่คุณสามารถส่งรูปภาพหรือไฟล์ PDF มาให้ผมช่วยแปลงเป็นข้อความได้เลยนะครับ! 📸📄"


chat_service = ChatService()
