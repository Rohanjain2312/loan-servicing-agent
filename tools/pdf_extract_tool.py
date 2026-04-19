from langchain_core.tools import tool
import fitz  # PyMuPDF
import os


@tool
def pdf_extract_tool(file_path: str) -> dict:
    """Extract raw text, page count, and word count from a PDF file using PyMuPDF."""
    try:
        if not os.path.exists(file_path):
            return {
                "raw_text": None,
                "page_count": 0,
                "word_count": 0,
                "error": f"File not found: {file_path}",
            }

        try:
            doc = fitz.open(file_path)
        except fitz.FileDataError as e:
            return {
                "raw_text": None,
                "page_count": 0,
                "word_count": 0,
                "error": f"Not a valid PDF: {str(e)}",
            }
        except Exception as e:
            return {
                "raw_text": None,
                "page_count": 0,
                "word_count": 0,
                "error": f"Failed to open PDF: {str(e)}",
            }

        if doc.is_encrypted:
            doc.close()
            return {
                "raw_text": None,
                "page_count": 0,
                "word_count": 0,
                "error": "PDF is encrypted and cannot be read without a password.",
            }

        page_count = len(doc)
        pages_text: list[str] = []

        for page_num in range(page_count):
            page = doc.load_page(page_num)
            text = page.get_text("text")
            pages_text.append(text)

        doc.close()

        raw_text = "\n".join(pages_text).strip()

        if not raw_text:
            return {
                "raw_text": "",
                "page_count": page_count,
                "word_count": 0,
                "error": "PDF has no extractable text layer (may be a scanned image).",
            }

        word_count = len(raw_text.split())

        return {
            "raw_text": raw_text,
            "page_count": page_count,
            "word_count": word_count,
            "error": None,
        }

    except Exception as e:
        return {
            "raw_text": None,
            "page_count": 0,
            "word_count": 0,
            "error": f"Unexpected error: {str(e)}",
        }
