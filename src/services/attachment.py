"""Attachment processing service for the email agent.
Handles:
- Security/virus scanning (EICAR signatures and executable extensions)
- Text extraction for various formats (TXT, CSV, JSON, HTML, Markdown, PDF)
- Local PII analysis using the privacy gateway
"""
from __future__ import annotations
import logging
import os
from typing import Optional
from src.services.pii import PrivacyGateway
log = logging.getLogger(__name__)
def scan_security(filename: str, payload: bytes) -> tuple[bool, str]:
    """Scan an attachment for safety and malicious patterns.
    Checks:
    - Executable/scripting extensions (.exe, .bat, .sh, .js, etc.)
    - EICAR antivirus test signature
    """
    if not filename:
        return True, "Clean scan: No filename provided."
    ext = os.path.splitext(filename)[1].lower()
    
    # 1. Executable or scripting extensions check
    dangerous_extensions = {
        ".exe", ".bat", ".cmd", ".sh", ".vbs", ".js", ".scr", 
        ".msi", ".dll", ".com", ".pif", ".wsf", ".hta", ".cpl"
    }
    if ext in dangerous_extensions:
        return False, f"Threat blocked: Executable or scripting file extension '{ext}' detected."
    # 2. EICAR standard antivirus test signature check
    eicar_signature = "X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    try:
        # Decode as utf-8 ignore-errors to search for the ASCII signature
        content_str = payload.decode("utf-8", errors="ignore")
        if eicar_signature in content_str:
            return False, "Threat blocked: EICAR standard antivirus test signature detected."
    except Exception as e:
        log.warning(f"Error checking EICAR signature for '{filename}': {e}")
    return True, "Clean scan: No threats detected."
def extract_text(payload: bytes, content_type: str, filename: str) -> Optional[str]:
    """Attempt to extract readable plain text from attachment bytes.
    Supports:
    - Text files (.txt, .md, .csv, .tsv, .json, .xml, .yaml, .yml)
    - HTML files
    - PDF files (requires pypdf)
    """
    if not filename:
        return None
    ext = os.path.splitext(filename)[1].lower()
    ct = content_type.lower()
    # 1. Plain text and common structured data files
    text_extensions = {
        ".txt", ".csv", ".tsv", ".json", ".xml", ".md", 
        ".html", ".htm", ".ini", ".yaml", ".yml", ".py", ".js", ".css"
    }
    is_text = ext in text_extensions or ct.startswith("text/") or ct in {
        "application/json", "application/xml", "application/javascript"
    }
    if is_text:
        encodings = ["utf-8", "latin-1", "cp1252", "utf-16"]
        for enc in encodings:
            try:
                return payload.decode(enc)
            except UnicodeDecodeError:
                continue
        # Fallback to utf-8 with replacement chars
        return payload.decode("utf-8", errors="replace")
    # 2. PDF documents
    if ext == ".pdf" or ct == "application/pdf":
        try:
            import pypdf
            import io
            reader = pypdf.PdfReader(io.BytesIO(payload))
            pages_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            return "\n".join(pages_text) if pages_text else ""
        except ImportError:
            log.warning(f"Could not extract PDF '{filename}': 'pypdf' package is not installed.")
            return None
        except Exception as e:
            log.warning(f"Failed to extract text from PDF '{filename}': {e}")
            return None
    return None
def detect_pii(text: str) -> list[str]:
    """Scan the extracted attachment text for Personally Identifiable Information (PII)."""
    if not text:
        return []
        
    try:
        gateway = PrivacyGateway()
        result = gateway.mask_text(text)
        return result.found_types
    except Exception as e:
        log.warning(f"Error checking PII in attachment: {e}")
        return []
