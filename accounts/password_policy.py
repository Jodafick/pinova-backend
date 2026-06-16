"""
Politique mot de passe Fotoce — validateur unique, messages clairs FR/EN.
"""

from __future__ import annotations

import re
from typing import Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

PASSWORD_MIN_LENGTH = 8
PASSWORD_VALID_EXAMPLE = 'Fotoce2026'

# Une règle = un identifiant stable + un message par langue (FR canonique côté API).
PASSWORD_RULES: tuple[dict[str, Any], ...] = (
    {
        'id': 'min_length',
        'messages': {
            'fr': 'Au moins 8 caractères.',
            'en': 'At least 8 characters.',
        },
    },
    {
        'id': 'has_letter',
        'messages': {
            'fr': 'Au moins une lettre.',
            'en': 'At least one letter.',
        },
    },
    {
        'id': 'has_digit',
        'messages': {
            'fr': 'Au moins un chiffre.',
            'en': 'At least one digit.',
        },
    },
    {
        'id': 'not_trivial',
        'messages': {
            'fr': 'Mot de passe trop simple ou trop proche de votre identifiant.',
            'en': 'Password is too simple or too close to your account identifier.',
        },
    },
)

RULE_MESSAGES_BY_ID: dict[str, dict[str, str]] = {
    rule['id']: rule['messages'] for rule in PASSWORD_RULES
}

TRIVIAL_PASSWORDS = frozenset(
    {
        'password',
        'password1',
        'password123',
        '12345678',
        '123456789',
        '1234567890',
        'qwerty123',
        'azerty123',
        'admin123',
        'letmein1',
        'welcome1',
        'fotoce',
        'fotoce123',
        'changeme',
        'changeme1',
        'iloveyou',
        'monmotdepasse',
        'motdepasse',
        'abcdefgh',
        'abc12345',
    }
)

_LETTER_RE = re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿ]', re.UNICODE)
_DIGIT_RE = re.compile(r'\d')


def resolve_password_lang(lang: str | None) -> str:
    code = (lang or 'fr').strip().lower().split('-', 1)[0]
    return code if code in ('fr', 'en') else 'fr'


def password_rule_message(rule_id: str, lang: str | None = None) -> str:
    messages = RULE_MESSAGES_BY_ID.get(rule_id, {})
    code = resolve_password_lang(lang)
    return messages.get(code) or messages.get('fr') or rule_id


def get_password_rules_payload(lang: str | None = None) -> dict[str, Any]:
    code = resolve_password_lang(lang)
    return {
        'min_length': PASSWORD_MIN_LENGTH,
        'valid_example': PASSWORD_VALID_EXAMPLE,
        'rules': [
            {
                'id': rule['id'],
                'message': rule['messages'].get(code) or rule['messages']['fr'],
            }
            for rule in PASSWORD_RULES
        ],
    }


def _normalize(value: str | None) -> str:
    return (value or '').strip().lower()


def _email_local_part(email: str | None) -> str:
    raw = _normalize(email)
    if '@' not in raw:
        return raw
    return raw.split('@', 1)[0]


def _is_trivial_password(
    password: str,
    *,
    email: str | None = None,
    username: str | None = None,
) -> bool:
    lowered = _normalize(password)
    if not lowered:
        return True
    if lowered in TRIVIAL_PASSWORDS:
        return True

    candidates = {_normalize(username), _normalize(email), _email_local_part(email)}
    candidates.discard('')
    for candidate in candidates:
        if not candidate:
            continue
        if lowered == candidate:
            return True
        if len(candidate) >= 4 and candidate in lowered:
            return True
    return False


def evaluate_fotoce_password(
    password: str,
    *,
    email: str | None = None,
    username: str | None = None,
) -> list[str]:
    """Retourne la liste des identifiants de règles non respectées."""
    failed: list[str] = []
    value = password or ''

    if len(value) < PASSWORD_MIN_LENGTH:
        failed.append('min_length')
    if not _LETTER_RE.search(value):
        failed.append('has_letter')
    if not _DIGIT_RE.search(value):
        failed.append('has_digit')
    if _is_trivial_password(value, email=email, username=username):
        failed.append('not_trivial')
    return failed


def validate_fotoce_password(
    password: str,
    *,
    user=None,
    email: str | None = None,
    username: str | None = None,
    lang: str | None = None,
) -> None:
    if user is not None:
        email = email or getattr(user, 'email', None)
        username = username or getattr(user, 'username', None)

    failed = evaluate_fotoce_password(password, email=email, username=username)
    if not failed:
        return

    errors = [
        ValidationError(password_rule_message(rule_id, lang), code=rule_id)
        for rule_id in failed
    ]
    raise ValidationError(errors)


def format_password_validation_errors(exc: ValidationError, lang: str | None = None) -> list[str]:
    messages: list[str] = []
    if hasattr(exc, 'error_list'):
        for error in exc.error_list:
            code = getattr(error, 'code', None)
            if code in RULE_MESSAGES_BY_ID:
                messages.append(password_rule_message(code, lang))
            else:
                messages.append(str(error))
        return messages

    code = getattr(exc, 'code', None)
    if code in RULE_MESSAGES_BY_ID:
        return [password_rule_message(code, lang)]
    return [str(exc)]


class FotocePasswordValidator:
    """Validateur Django unique — remplace les validateurs par défaut."""

    def validate(self, password, user=None):
        validate_fotoce_password(password, user=user)

    def get_help_text(self):
        return _('Votre mot de passe doit respecter la politique Fotoce (8 caractères, lettre + chiffre).')
