"""PDF utility functions."""

import io
import logging
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


def extract_first_pages(pdf_bytes: bytes, max_pages: int = 10) -> bytes:
    """Extract only the first N pages from a PDF.

    This reduces file size for large PDFs before sending to OCR.

    Args:
        pdf_bytes: Original PDF content as bytes
        max_pages: Maximum number of pages to extract (default: 10)

    Returns:
        New PDF with only first max_pages pages as bytes

    Raises:
        Exception: If PDF cannot be processed
    """
    try:
        # Read the PDF
        pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
        total_pages = len(pdf_reader.pages)

        logger.info(f"PDF has {total_pages} pages, extracting first {max_pages}")

        # If PDF has fewer pages than max, return original
        if total_pages <= max_pages:
            logger.info(f"PDF has {total_pages} pages (<= {max_pages}), using original")
            return pdf_bytes

        # Create a new PDF with only first max_pages
        pdf_writer = PdfWriter()

        for page_num in range(min(max_pages, total_pages)):
            pdf_writer.add_page(pdf_reader.pages[page_num])

        # Write to bytes
        output = io.BytesIO()
        pdf_writer.write(output)
        output.seek(0)

        result_bytes = output.read()
        logger.info(
            f"Extracted {min(max_pages, total_pages)} pages: "
            f"original={len(pdf_bytes)} bytes, new={len(result_bytes)} bytes"
        )

        return result_bytes

    except Exception as e:
        logger.error(f"Error extracting PDF pages: {e}", exc_info=True)
        # Return original PDF if extraction fails
        logger.warning("Falling back to original PDF")
        return pdf_bytes
