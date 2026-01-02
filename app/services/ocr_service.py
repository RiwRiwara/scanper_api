from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, AnalyzeResult
from azure.core.credentials import AzureKeyCredential

from app.config import settings


class OCRService:
    def __init__(self):
        self.client = DocumentIntelligenceClient(
            endpoint=settings.AZURE_DOC_INTEL_ENDPOINT,
            credential=AzureKeyCredential(settings.AZURE_DOC_INTEL_KEY),
        )

    def extract_text_from_url(self, image_url: str) -> str:
        """Extract text from image URL using Azure Document Intelligence."""
        poller = self.client.begin_analyze_document(
            model_id="prebuilt-read",
            analyze_request=AnalyzeDocumentRequest(url_source=image_url),
        )
        result: AnalyzeResult = poller.result()
        return self._format_result(result)

    def extract_text_from_bytes(self, image_bytes: bytes) -> str:
        """Extract text from image bytes using Azure Document Intelligence."""
        poller = self.client.begin_analyze_document(
            model_id="prebuilt-read",
            analyze_request=image_bytes,
            content_type="application/octet-stream",
        )
        result: AnalyzeResult = poller.result()
        return self._format_result(result)

    def _format_result(self, result: AnalyzeResult) -> str:
        """Format the OCR result into readable text."""
        if not result.content:
            return "No text found in image."

        return result.content


ocr_service = OCRService()
