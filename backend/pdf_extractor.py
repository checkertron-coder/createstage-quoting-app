"""
PDF Text Extractor — Session 7.

Extracts text content from uploaded PDF bid documents using pdfplumber.
pdfplumber handles tables and complex layouts better than PyPDF2.

Does NOT implement OCR — if a PDF is scanned images, it flags
extraction_quality as "poor" and warns the user.
"""

import io
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

MAX_PAGES = 500
MAX_FILE_SIZE_MB = 50


class PDFExtractor:
    """
    Extracts text content from PDF bid documents.
    Uses pdfplumber for text extraction.
    """

    def extract_text(self, file_path: str) -> dict:
        """
        Extract text from a PDF file on disk.

        Returns: {
            "text": str,
            "page_count": int,
            "file_size_mb": float,
            "extraction_quality": str,  # "good" | "fair" | "poor"
        }
        """
        # Check file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        # Check file size
        file_size = os.path.getsize(file_path)
        file_size_mb = round(file_size / (1024 * 1024), 2)
        if file_size_mb > MAX_FILE_SIZE_MB:
            raise ValueError(
                f"File too large: {file_size_mb} MB (max {MAX_FILE_SIZE_MB} MB)"
            )

        # Check extension
        if not file_path.lower().endswith(".pdf"):
            raise ValueError("File must be a PDF")

        return self._extract(file_path=file_path, file_size_mb=file_size_mb)

    def extract_text_from_bytes(self, file_bytes: bytes, filename: str = "upload.pdf") -> dict:
        """
        Extract text from in-memory bytes (for API upload).

        Returns same dict as extract_text.
        """
        file_size_mb = round(len(file_bytes) / (1024 * 1024), 2)
        if file_size_mb > MAX_FILE_SIZE_MB:
            raise ValueError(
                f"File too large: {file_size_mb} MB (max {MAX_FILE_SIZE_MB} MB)"
            )

        return self._extract(file_bytes=file_bytes, file_size_mb=file_size_mb)

    def _extract(
        self,
        file_path: str = None,
        file_bytes: bytes = None,
        file_size_mb: float = 0.0,
    ) -> dict:
        """Internal extraction logic."""
        import pdfplumber

        pages_text = []
        page_count = 0

        try:
            if file_path:
                pdf = pdfplumber.open(file_path)
            else:
                pdf = pdfplumber.open(io.BytesIO(file_bytes))

            with pdf:
                page_count = len(pdf.pages)

                if page_count > MAX_PAGES:
                    raise ValueError(
                        f"PDF has {page_count} pages (max {MAX_PAGES})"
                    )

                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages_text.append(text)

        except ValueError:
            raise  # Re-raise our validation errors
        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
            raise ValueError(f"Failed to read PDF: {str(e)}")

        full_text = "\n\n".join(pages_text)

        # Assess extraction quality
        extraction_quality = self._assess_quality(
            full_text, page_count,
        )

        return {
            "text": full_text,
            "page_count": page_count,
            "file_size_mb": file_size_mb,
            "extraction_quality": extraction_quality,
        }

    def _assess_quality(self, text: str, page_count: int) -> str:
        """
        Assess extraction quality based on text density.

        "good": > 100 chars per page average
        "fair": 20-100 chars per page
        "poor": < 20 chars per page (likely scanned/image PDF)
        """
        if page_count == 0:
            return "poor"

        chars_per_page = len(text) / page_count

        if chars_per_page > 100:
            return "good"
        elif chars_per_page > 20:
            return "fair"
        else:
            return "poor"
