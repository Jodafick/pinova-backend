"""

Locale utilisateur pour les messages d’erreur API lisibles dans le corps (400).



Le client envoie sa langue (priorité à ``X-Fotoce-Lang``, alignée RN / Vue).

Les textes restent canoniques **en français** ; ``translate_text_to`` applique googletrans +

cache BD (``MachineTranslationCache``).

"""



from __future__ import annotations



import logging

import re



from .translation_cache import normalize_translation_dest



logger = logging.getLogger(__name__)



API_LOCALE_LANG_RE = re.compile(r'^[a-z][a-z0-9_-]{0,21}$')





def api_locale_from_request(request) -> str:

    """

    Code langue « logique » (ex. ``fr``, ``en``, ``fon``, ``bn``…).

    Préfixe BCP‑47 avant ``-``.

    """

    if request:

        raw_x = request.META.get('HTTP_X_FOTOCE_LANG') or request.META.get('HTTP_X_PINOVA_LANG') or ''

        raw_x = raw_x.strip().split(';')[0].strip()

        base = raw_x.split('-', 1)[0].strip().lower()

        if base and API_LOCALE_LANG_RE.match(base):

            return base[:24]



        al = request.META.get('HTTP_ACCEPT_LANGUAGE') or ''

        al = al.strip().lower()

        if al:

            first = al.split(',', 1)[0].strip()

            lang = first.split(';', 1)[0].strip().split('-', 1)[0].strip().lower()

            if lang and API_LOCALE_LANG_RE.match(lang):

                return lang[:24]



    return 'fr'





def localize_api_user_message(canonical_fr: str, request) -> str:

    """Français canonique → langue cliente (`translate_text_to` + cache)."""

    text = (canonical_fr or '').strip()

    if not text:

        return ''



    lang = api_locale_from_request(request)

    if lang == 'fr' or normalize_translation_dest(lang) == 'fr':

        return text



    try:

        from asgiref.sync import async_to_sync

        from googletrans import Translator



        from .translation import translate_text_to



        translator = Translator()

        out = async_to_sync(translate_text_to)(translator, text, lang, 'fr')

        return (out or text).strip()

    except Exception as exc:

        logger.warning(

            'localize_api_user_message: impossible de traduire vers lang=%s — %s',

            lang,

            exc,

            exc_info=False,

        )

        return text

