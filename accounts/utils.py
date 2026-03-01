import random
import string
import logging
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


# ------------------------------------------------
# OTP + Token Generators
# ------------------------------------------------
def _otp_code(length=None):
    """Generate a numeric OTP of configured length."""
    length = length or settings.OTP_LENGTH
    start = 10 ** (length - 1)
    end = (10 ** length) - 1
    return str(random.randint(start, end))


def generate_reset_token(length=48):
    """Generate secure random reset token."""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))


# ------------------------------------------------
# Cache Key Builders (clean & namespaced)
# ------------------------------------------------
def otp_cache_key(target: str) -> str:
    """
    Key storing the actual OTP.
    Eg: otp:user@example.com or otp:+919876543210
    """
    return f"otp:{target}"


def otp_attempts_key(target: str) -> str:
    """
    Key tracking OTP verification attempts.
    """
    return f"otp_attempts:{target}"


def otp_request_count_key(target: str) -> str:
    """
    Key tracking OTP request count per hour.
    """
    return f"otp_req_count:{target}"


def reset_token_cache_key(token: str) -> str:
    """
    Key for password reset tokens.
    """
    return f"reset_token:{token}"


# send OTP (email). Replace or add SMS sending logic as needed.
# def send_otp_via_email(email, otp):
#     subject = "Your password reset code"
#     message = f"Your password reset OTP is: {otp}. It is valid for {settings.OTP_TTL_SECONDS // 60} minutes."
#     from_email = settings.DEFAULT_FROM_EMAIL
#     try:
#         send_mail(subject, message, from_email, [email], fail_silently=False)
#         logger.info("OTP email sent to %s", email)
#     except Exception as e:
#         logger.exception("Failed to send OTP email to %s: %s", email, str(e))
#         raise
