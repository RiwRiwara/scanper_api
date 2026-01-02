import logging
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, AnalyzeResult
from azure.core.credentials import AzureKeyCredential

from app.config import settings
from app.utils import extract_first_pages

logger = logging.getLogger(__name__)


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

    def extract_text_from_pdf_bytes(self, pdf_bytes: bytes, max_pages: int = 10) -> str:
        """Extract text from PDF bytes using Azure Document Intelligence.

        Args:
            pdf_bytes: PDF file content as bytes
            max_pages: Maximum number of pages to process (default: 10)

        Returns:
            Extracted text from the PDF with page numbers (first max_pages only)
        """
        # Extract only first max_pages to reduce file size
        # This solves Azure's file size limit for large PDFs
        logger.info(f"Extracting first {max_pages} pages from PDF")
        reduced_pdf = extract_first_pages(pdf_bytes, max_pages=max_pages)

        logger.info(
            f"Sending to Azure: original={len(pdf_bytes)} bytes, "
            f"reduced={len(reduced_pdf)} bytes"
        )

        poller = self.client.begin_analyze_document(
            model_id="prebuilt-read",
            body=reduced_pdf,
            content_type="application/pdf",
        )
        result: AnalyzeResult = poller.result()

        # Get pages in document
        if not result.pages:
            return "No text found in PDF."

        # Format text page by page
        formatted_output = []

        for page in result.pages:
            page_number = page.page_number

            # Extract lines from this page
            page_text = []
            if result.paragraphs:
                # Get paragraphs that belong to this page
                for paragraph in result.paragraphs:
                    # Check if paragraph is on this page
                    if paragraph.bounding_regions:
                        for region in paragraph.bounding_regions:
                            if region.page_number == page_number:
                                page_text.append(paragraph.content)
                                break

            # If no paragraphs found, use the content spans
            if not page_text and result.content:
                # Fall back to extracting text from page lines
                if page.lines:
                    page_text = [line.content for line in page.lines]

            # Format page section
            page_section = f"━━━━━ หน้า {page_number} ━━━━━\n\n"

            if page_text:
                page_section += "\n\n".join(page_text)
            else:
                page_section += "(ไม่พบข้อความในหน้านี้)"

            formatted_output.append(page_section)

        return "\n\n".join(formatted_output)

    def _format_result(self, result: AnalyzeResult) -> str:
        """Format the OCR result into readable text."""
        if not result.content:
            return "No text found in image."

        return result.content


ocr_service = OCRService()
