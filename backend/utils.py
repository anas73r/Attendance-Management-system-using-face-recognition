# backend/utils.py

import logging

logger = logging.getLogger(__name__)

def normalize_student_id(student_id):
    """
    Robust normalization of student IDs to ensure consistent matching.
    - Handles int, float, and strings.
    - Removes trailing .0 (often added by Excel or pandas).
    - Strips whitespace.
    - Converts to uppercase for case-insensitive matching.
    """
    if student_id is None:
        return ""
    
    # Convert to string and strip whitespace
    sid = str(student_id).strip()
    
    # Remove trailing .0 if present (e.g., "101.0" -> "101")
    if sid.endswith(".0"):
        sid = sid[:-2]
    
    # Convert to uppercase for case-insensitivity
    return sid.upper()
