import random
import time
import base64
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.core.cache import cache
from django.core.exceptions import ValidationError

SIGNER_SALT = 'innvetrix-captcha-security-2026'

def generate_svg_challenge(text):
    """
    Renders the security arithmetic puzzle as an obfuscated SVG image
    with randomized noise lines to defeat automated text parsers and OCR scrapers.
    """
    lines = []
    for _ in range(5):
        x1 = random.randint(5, 145)
        y1 = random.randint(5, 38)
        x2 = random.randint(5, 145)
        y2 = random.randint(5, 38)
        opacity = round(random.uniform(0.18, 0.40), 2)
        lines.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#f59e0b" stroke-width="1" stroke-opacity="{opacity}" />')

    noise_svg = "\n    ".join(lines)
    
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="150" height="42" viewBox="0 0 150 42">
    <rect width="100%" height="100%" rx="8" fill="#0f172a" stroke="rgba(245, 158, 11, 0.4)" stroke-width="1"/>
    {noise_svg}
    <text x="50%" y="60%" text-anchor="middle" dominant-baseline="middle" fill="#f59e0b" font-family="'Courier New', Courier, monospace" font-weight="bold" font-size="19" letter-spacing="2">{text}</text>
</svg>"""

    encoded = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
    return f"data:image/svg+xml;base64,{encoded}"


def generate_captcha():
    """
    Generates a dynamic arithmetic challenge, renders SVG image,
    and returns signed token with 10-minute validity.
    """
    # 70% addition, 30% subtraction
    if random.random() < 0.7:
        a = random.randint(4, 25)
        b = random.randint(2, 19)
        answer = a + b
        challenge_text = f"{a} + {b} = ?"
    else:
        a = random.randint(12, 35)
        b = random.randint(3, a - 1)
        answer = a - b
        challenge_text = f"{a} - {b} = ?"

    timestamp = int(time.time())
    payload = f"{answer}:{timestamp}"
    
    signer = TimestampSigner(salt=SIGNER_SALT)
    signed_token = signer.sign(payload)

    svg_data_uri = generate_svg_challenge(challenge_text)

    return {
        'challenge_svg': svg_data_uri,
        'challenge_text': challenge_text,
        'token': signed_token,
    }


def verify_captcha(user_answer, token, max_age_seconds=600, min_age_seconds=1.5):
    """
    Validates the submitted answer against the cryptographically signed token.
    Enforces expiration, signature integrity, and timing defense against bots.
    """
    if not token or not str(token).strip():
        raise ValidationError("Security challenge verification token is missing. Please refresh.")

    if not user_answer or not str(user_answer).strip():
        raise ValidationError("Please solve the security challenge to verify you are human.")

    signer = TimestampSigner(salt=SIGNER_SALT)
    try:
        unsigned_payload = signer.unsign(token, max_age=max_age_seconds)
    except SignatureExpired:
        raise ValidationError("Security challenge has expired. Please refresh the challenge.")
    except BadSignature:
        raise ValidationError("Invalid or tampered security token. Please refresh.")

    try:
        expected_answer_str, timestamp_str = unsigned_payload.split(':', 1)
        expected_answer = int(expected_answer_str)
        created_timestamp = int(timestamp_str)
    except (ValueError, IndexError):
        raise ValidationError("Malformed security token. Please refresh.")

    # Timing defense: detect superhuman submission speeds (< 1.5 seconds)
    elapsed = time.time() - created_timestamp
    if elapsed < min_age_seconds:
        raise ValidationError("Submission was too rapid. Automated submissions are blocked.")

    # Validate numeric answer
    try:
        cleaned_user_answer = int(str(user_answer).strip())
    except ValueError:
        raise ValidationError("The security answer must be a valid number.")

    if cleaned_user_answer != expected_answer:
        raise ValidationError("Incorrect security answer. Please solve the calculation.")

    return True


def check_ip_rate_limit(ip_address, max_requests=25, window_seconds=600):
    """
    Prevents brute-force form submission flooding from a single IP.
    Returns True if permitted, False if rate limit is exceeded.
    """
    if not ip_address:
        return True

    from django.conf import settings
    if getattr(settings, 'DEBUG', False) and ip_address in ('127.0.0.1', 'localhost', '::1'):
        return True

    cache_key = f"inquiry_rate_limit_{ip_address}"
    current_count = cache.get(cache_key, 0)

    if current_count >= max_requests:
        return False

    cache.set(cache_key, current_count + 1, timeout=window_seconds)
    return True
