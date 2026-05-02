import logging
import os
import re
from functools import lru_cache

from babel.numbers import get_currency_symbol
from babel.numbers import get_territory_currencies
import requests
from currency_converter import CurrencyConverter

logger = logging.getLogger(__name__)

# Currencies offered in user preferences.
SUPPORTED_CURRENCIES = [
    'USD', 'EUR', 'GBP', 'CAD', 'AUD', 'NZD',
    'CHF', 'SEK', 'NOK', 'DKK',
    'JPY', 'CNY', 'HKD', 'SGD', 'KRW', 'INR',
    'AED', 'SAR', 'QAR', 'TRY', 'ILS',
    'ZAR', 'NGN', 'KES', 'GHS', 'EGP', 'MAD', 'TND', 'XOF', 'XAF',
    'BRL', 'MXN', 'ARS', 'CLP', 'COP', 'PEN',
    'RUB', 'UAH', 'PLN', 'CZK', 'HUF', 'RON',
    'THB', 'MYR', 'IDR', 'PHP', 'VND', 'PKR', 'BDT',
    'KWD', 'BHD', 'OMR', 'JOD', 'LKR',
    'DZD', 'UGX', 'TZS', 'ZMW', 'ETB',
]

ZERO_DECIMAL_CURRENCIES = {'XOF', 'XAF', 'JPY', 'KRW', 'CLP'}

# Minimal country -> currency mapping for default user preference.
COUNTRY_TO_CURRENCY = {
    'BJ': 'XOF', 'TG': 'XOF', 'SN': 'XOF', 'CI': 'XOF', 'BF': 'XOF', 'ML': 'XOF', 'NE': 'XOF', 'GW': 'XOF',
    'CM': 'XAF', 'GA': 'XAF', 'CG': 'XAF', 'CF': 'XAF', 'TD': 'XAF', 'GQ': 'XAF',
    'FR': 'EUR', 'DE': 'EUR', 'ES': 'EUR', 'IT': 'EUR', 'PT': 'EUR', 'NL': 'EUR', 'BE': 'EUR', 'IE': 'EUR',
    'GB': 'GBP',
    'US': 'USD', 'CA': 'CAD',
    'NG': 'NGN', 'GH': 'GHS', 'KE': 'KES', 'ZA': 'ZAR', 'MA': 'MAD', 'TN': 'TND', 'EG': 'EGP',
    'IN': 'INR', 'CN': 'CNY', 'JP': 'JPY', 'KR': 'KRW', 'AE': 'AED', 'SA': 'SAR', 'QA': 'QAR',
    'BR': 'BRL', 'MX': 'MXN', 'AR': 'ARS', 'CL': 'CLP', 'CO': 'COP', 'PE': 'PEN',
    'CH': 'CHF', 'SE': 'SEK', 'NO': 'NOK', 'DK': 'DKK', 'PL': 'PLN', 'CZ': 'CZK', 'HU': 'HUF', 'RO': 'RON',
    'TR': 'TRY', 'IL': 'ILS', 'RU': 'RUB', 'UA': 'UAH',
    'AU': 'AUD', 'NZ': 'NZD', 'SG': 'SGD', 'HK': 'HKD',
}

_offline_currency_converter = CurrencyConverter(fallback_on_missing_rate=True)


def normalize_currency(code):
    value = (code or '').strip().upper()
    return value if value in SUPPORTED_CURRENCIES else None


@lru_cache(maxsize=1)
def currency_choices_with_symbols():
    choices = []
    for code in SUPPORTED_CURRENCIES:
        try:
            symbol = get_currency_symbol(code)
        except Exception:
            symbol = code
        label = f'{code} ({symbol})' if symbol and symbol != code else code
        choices.append((code, label))
    return choices


def parse_country_from_accept_language(accept_language):
    if not accept_language:
        return None
    # Examples: fr-FR, en-US;q=0.9, pt-BR
    match = re.search(r'[a-z]{2}-([a-zA-Z]{2})', accept_language)
    if match:
        return match.group(1).upper()
    return None


def infer_country_code(request):
    headers = request.META
    candidates = [
        headers.get('HTTP_CF_IPCOUNTRY'),   # Cloudflare
        headers.get('HTTP_X_COUNTRY_CODE'),
        headers.get('GEOIP_COUNTRY_CODE'),
        parse_country_from_accept_language(headers.get('HTTP_ACCEPT_LANGUAGE', '')),
    ]
    for code in candidates:
        value = (code or '').strip().upper()
        if len(value) == 2 and value.isalpha():
            return value
    return None


def default_currency_for_country(country_code):
    if not country_code:
        return 'XOF'
    country = country_code.upper()
    mapped = COUNTRY_TO_CURRENCY.get(country)
    if mapped:
        return mapped
    try:
        # Babel gives the default legal tender currency for a territory.
        currencies = get_territory_currencies(country, tender=True)
        for code in currencies:
            normalized = normalize_currency(code)
            if normalized:
                return normalized
    except Exception:
        logger.exception('Unable to infer currency from territory %s', country)
    return 'USD'


def decimals_for_currency(currency_iso):
    return 0 if (currency_iso or '').upper() in ZERO_DECIMAL_CURRENCIES else 2


@lru_cache(maxsize=512)
def _cached_rate(base, quote):
    base_code = (base or '').upper()
    quote_code = (quote or '').upper()
    if not base_code or not quote_code:
        raise ValueError('Invalid currency pair')
    if base_code == quote_code:
        return 1.0

    # Primary: live rates API.
    api_url = os.environ.get('CURRENCY_RATES_API_URL', 'https://open.er-api.com/v6/latest').rstrip('/')
    timeout = int(os.environ.get('CURRENCY_RATES_TIMEOUT_SECONDS', '8'))
    try:
        response = requests.get(f'{api_url}/{base_code}', timeout=timeout)
        response.raise_for_status()
        payload = response.json() or {}
        rates = payload.get('rates') or {}
        rate_value = rates.get(quote_code)
        if isinstance(rate_value, (int, float)) and rate_value > 0:
            return float(rate_value)
    except Exception:
        logger.exception('Live FX provider failed for %s/%s', base_code, quote_code)

    # Fallback: offline ECB data.
    try:
        converted = _offline_currency_converter.convert(1, base_code, quote_code)
        return float(converted)
    except Exception:
        logger.exception('Offline FX fallback failed for %s/%s', base_code, quote_code)
        raise


def convert_minor_amount(amount_minor, from_currency, to_currency):
    src = (from_currency or '').upper()
    dst = (to_currency or '').upper()
    if not src or not dst:
        return int(amount_minor)
    if src == dst:
        return int(amount_minor)

    src_decimals = decimals_for_currency(src)
    dst_decimals = decimals_for_currency(dst)
    amount_major = float(amount_minor) / (10 ** src_decimals)
    try:
        rate = _cached_rate(src, dst)
        converted_major = amount_major * rate
        return int(round(converted_major * (10 ** dst_decimals)))
    except Exception:
        logger.exception('Currency conversion failed from %s to %s', src, dst)
        return None

