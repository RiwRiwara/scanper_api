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
            body=image_bytes,
            content_type="application/octet-stream",
        )
        result: AnalyzeResult = poller.result()
        return self._format_result(result)

    def extract_text_from_pdf_bytes(self, pdf_bytes: bytes, max_pages: int = 5) -> str:
        """Extract text from PDF bytes using Azure Document Intelligence.

        Args:
            pdf_bytes: PDF file content as bytes
            max_pages: Maximum number of pages to process (default: 5)

        Returns:
            Extracted text from the PDF (first max_pages only)
        """
        poller = self.client.begin_analyze_document(
            model_id="prebuilt-read",
            body=pdf_bytes,
            content_type="application/pdf",
            pages=f"1-{max_pages}",  # Only process first max_pages pages
        )
        result: AnalyzeResult = poller.result()

        # Get total pages in document
        total_pages = len(result.pages) if result.pages else 0

        formatted_text = self._format_result(result)

        # Add page info header
        if total_pages > 0:
            header = f"Processed {total_pages} page(s) (First {max_pages} pages only)\n"
            header += "=" * 50 + "\n\n"
            return header + formatted_text

        return formatted_text

    def _format_result(self, result: AnalyzeResult) -> str:
        """Format the OCR result into readable text."""
        if not result.content:
            return "No text found in image."

        return result.content


ocr_service = OCRService()
