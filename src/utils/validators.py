import re
from urllib.parse import urlparse
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass


def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """
    Validate email address format

    Args:
        email: Email address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not email:
        return False, "Email is required"

    # remove whitespace
    email = email.strip()

    # basic email regex pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    if not re.match(pattern, email):
        return False, f"Invalid email format: {email}"

    # check for common typos
    if email.endswith('.con') or email.endswith('.cmo'):
        return False, f"Possible typo in email domain: {email}"

    return True, None


def validate_url(url: str, require_https: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Validate URL format
    """
    if not url:
        return False, "URL is required"

    # Remove whitespace
    url = url.strip()

    try:
        result = urlparse(url)

        # check scheme and netloc exist
        if not all([result.scheme, result.netloc]):
            return False, f"Invalid URL format: {url}"

        # check scheme is http/https
        if result.scheme not in ['http', 'https']:
            return False, f"URL must use http or https protocol: {url}"

        # optionally require https
        if require_https and result.scheme != 'https':
            return False, f"URL must use https protocol: {url}"

        # check for localhost/private IPs in production
        private_patterns = ['localhost', '127.0.0.1', '0.0.0.0', '192.168.', '10.']
        if any(pattern in result.netloc for pattern in private_patterns):
            logger.warning(f"Private/local URL detected: {url}")

        return True, None

    except Exception as e:
        return False, f"URL parsing error: {str(e)}"


def validate_linkedin_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate LinkedIn profile URL
    """
    if not url:
        return True, None  # pptional field

    url = url.strip()

    # basic URL validation first
    is_valid, error = validate_url(url, require_https=True)
    if not is_valid:
        return False, error

    # check it's actually a LinkedIn URL
    if 'linkedin.com/in/' not in url.lower():
        return False, f"Not a valid LinkedIn profile URL: {url}"

    return True, None


def validate_text_length(
    text: str,
    min_len: int = 1,
    max_len: int = 50000,
    field_name: str = "Text"
) -> Tuple[bool, Optional[str]]:
    """
    Validate text length constraints
    """
    if not text:
        if min_len > 0:
            return False, f"{field_name} is required"
        return True, None

    text_len = len(text)

    if text_len < min_len:
        return False, f"{field_name} too short (minimum {min_len} characters, got {text_len})"

    if text_len > max_len:
        return False, f"{field_name} too long (maximum {max_len} characters, got {text_len})"

    return True, None


def validate_phone(phone: str) -> Tuple[bool, Optional[str]]:
    """
    Validate phone number format (basic validation)
    """
    if not phone:
        return True, None  # optional field

    phone = phone.strip()

    # remove common formatting characters
    clean_phone = re.sub(r'[\s\-\(\)\.]', '', phone)

    # check if it's digits only (with optional + at start)
    if not re.match(r'^\+?\d{7,15}$', clean_phone):
        return False, f"Invalid phone number format: {phone}"

    return True, None


def sanitize_text(text: str, max_len: int = 50000) -> str:
    """
    Sanitize text input by removing dangerous characters
    """
    if not text:
        return ""

    # remove null bytes (can cause issues with databases)
    text = text.replace('\x00', '')

    # remove other control characters except common whitespace
    text = re.sub(r'[\x01-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)

    # limit length
    if len(text) > max_len:
        text = text[:max_len]
        logger.warning(f"Text truncated to {max_len} characters")

    return text.strip()


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent directory traversal attacks
    """
    if not filename:
        return "untitled"

    # remove path separators and parent directory references
    filename = filename.replace('/', '_').replace('\\', '_')
    filename = filename.replace('..', '_')

    # remove other dangerous characters
    filename = re.sub(r'[<>:"|?*\x00-\x1F]', '_', filename)

    # limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:250] + ('.' + ext if ext else '')

    return filename


def validate_job_title(title: str) -> Tuple[bool, Optional[str]]:
    """
    Validate job title format
    """
    if not title:
        return False, "Job title is required"

    title = title.strip()

    # check minimum length
    if len(title) < 3:
        return False, f"Job title too short: {title}"

    # check maximum length
    if len(title) > 100:
        return False, f"Job title too long (max 100 characters): {title}"

    # check for suspicious patterns (SQL injection attempts)
    suspicious_patterns = ['--', ';', 'DROP', 'SELECT', 'INSERT', 'DELETE', 'UPDATE']
    title_upper = title.upper()
    if any(pattern in title_upper for pattern in suspicious_patterns):
        logger.warning(f"Suspicious pattern in job title: {title}")
        return False, "Invalid job title format"

    return True, None


def validate_company_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate company name format
    """
    if not name:
        return False, "Company name is required"

    name = name.strip()

    # check minimum length
    if len(name) < 2:
        return False, f"Company name too short: {name}"

    # check maximum length
    if len(name) > 200:
        return False, f"Company name too long (max 200 characters): {name}"

    return True, None


def validate_message_content(message: str, message_type: str = "linkedin_message") -> Tuple[bool, Optional[str]]:
    """
    Validate outreach message content
    """
    if not message:
        return False, "Message content is required"

    message = message.strip()

    # check minimum length
    if len(message) < 20:
        return False, f"Message too short (minimum 20 characters)"

    # check maximum length based on message type
    max_lengths = {
        'linkedin_connection': 300,
        'linkedin_message': 2000,
        'email': 10000
    }
    max_len = max_lengths.get(message_type, 5000)

    if len(message) > max_len:
        return False, f"Message too long (maximum {max_len} characters for {message_type})"

    return True, None


# convenience function for batch validation
def validate_contact_data(
    name: Optional[str] = None,
    email: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    phone: Optional[str] = None,
    title: Optional[str] = None
) -> Tuple[bool, list[str]]:
    """
    Validate all contact data fields at once
    """
    errors = []

    if name:
        is_valid, error = validate_text_length(name, min_len=2, max_len=100, field_name="Contact name")
        if not is_valid:
            errors.append(error)

    if email:
        is_valid, error = validate_email(email)
        if not is_valid:
            errors.append(error)

    if linkedin_url:
        is_valid, error = validate_linkedin_url(linkedin_url)
        if not is_valid:
            errors.append(error)

    if phone:
        is_valid, error = validate_phone(phone)
        if not is_valid:
            errors.append(error)

    if title:
        is_valid, error = validate_text_length(title, min_len=2, max_len=100, field_name="Job title")
        if not is_valid:
            errors.append(error)

    return len(errors) == 0, errors
