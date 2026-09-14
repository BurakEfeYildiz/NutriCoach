"""Opt-in local diagnostics: classify messages, never emit provider text or traces."""
import logging
import re

from app.core.config import Settings

logger = logging.getLogger('nutricoach.gemini')
SCHEMA_TERMS = ('response_json_schema', 'response_mime_type', 'additionalProperties', 'anyOf', 'oneOf', '$ref', '$defs', 'pattern', 'exclusiveMinimum', 'minimum', 'maximum', 'format', 'const', 'enum')


def log_provider_error(settings: Settings, error: Exception, *, structured: bool) -> None:
    if settings.app_environment != 'local' or not settings.gemini_diagnostics:
        return
    # Provider errors can echo prompts, credentials and model responses. Only static
    # classifications are emitted, even when the text appears harmless.
    message = str(error)
    lower = message.lower()
    reason = 'details_omitted'
    for phrases, label in (
        (('too many states', 'too complex', 'too many nesting', 'too deeply nested'), 'schema_complexity'),
        (('not supported', 'unsupported'), 'unsupported_feature'),
        (('unknown name', 'unknown field', 'unrecognized field'), 'unknown_field'),
        (('invalid argument', 'invalid_argument'), 'invalid_argument'),
        (('api_key_invalid',), 'invalid_api_key'),
        (('timed out', 'timeout'), 'timeout'),
    ):
        if any(phrase in lower for phrase in phrases):
            reason = label
            break
    fields = ','.join(term for term in SCHEMA_TERMS if term in message) or 'none'
    name = type(error).__name__
    name = name if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,79}', name) else 'Exception'
    code = getattr(error, 'code', None)
    code = code if isinstance(code, int) and 100 <= code <= 599 else None
    logger.warning('Gemini local diagnostic: exception=%s status=%s phase=%s reason=%s schema_terms=%s',
                   name, code, 'intent' if structured else 'coach', reason, fields)
