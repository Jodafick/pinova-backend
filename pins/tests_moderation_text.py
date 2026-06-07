"""Tests modération texte — vocabulaire courant autorisé, insultes violentes / porno bloqués."""

from django.test import SimpleTestCase

from pins.moderation import _profanity_in, validate_pin_text
from pins.text_blocklist import contains_blocked_text


class TextModerationPermissiveTests(SimpleTestCase):
    def test_everyday_french_vocabulary_allowed(self):
        for text in (
            'Mon pot de Mayo',
            'pot de confiture',
            'Éducation sexuelle',
            'le sexe des fleurs',
            'amour et sensualité',
            'what the fuck',  # frustration, pas une insulte ciblée
            'merde alors',
        ):
            with self.subTest(text=text):
                self.assertFalse(contains_blocked_text(text), text)
                self.assertFalse(_profanity_in(text), text)

    def test_violent_insults_blocked(self):
        for text in (
            'nique ta mère',
            'va te faire foutre',
            'fuck you',
            'fils de pute',
        ):
            with self.subTest(text=text):
                self.assertTrue(contains_blocked_text(text), text)
                self.assertTrue(_profanity_in(text), text)

    def test_explicit_porn_blocked(self):
        for text in (
            'lien pornhub gratuit',
            'gangbang video',
            'film porno complet',
        ):
            with self.subTest(text=text):
                self.assertTrue(contains_blocked_text(text), text)

    def test_validate_pin_title_allows_everyday_content(self):
        validate_pin_text('Mon pot de Mayo', 'Atelier éducation sexuelle', ['cuisine'], [])
