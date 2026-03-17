from __future__ import annotations

import base64
import hashlib
import hmac
import json
import platform
import random
import re
import time
from dataclasses import dataclass
from html import unescape
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from .config import Credentials


DEFAULT_DISCOVERY_URLS = (
    'http://www.gstatic.com/generate_204',
    'http://connect.rom.miui.com/generate_204',
    'http://detectportal.firefox.com/canonical.html',
    'https://login.ecnu.edu.cn/',
)
DEFAULT_BASE_URL = 'https://login.ecnu.edu.cn'
DEFAULT_CALLBACK_PREFIX = 'jQuery1124'
DEFAULT_ENC_VER = 'srun_bx1'
DEFAULT_N = '200'
DEFAULT_TYPE = '1'
SRUN_BASE64_ALPHABET = 'LVoJPiCN2R8G90yg+hmFHuacZ1OWMnrsSTXkYpUq/3dlbfKwv6xztjI7DeBE45QA'
STD_BASE64_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
META_REFRESH_RE = re.compile(
    r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\'][^"\']*url=([^"\']+)',
    re.IGNORECASE,
)
JSONP_RE = re.compile(r'^\s*([^(]+)\((.*)\)\s*;?\s*$', re.DOTALL)


@dataclass(frozen=True)
class PortalContext:
    ac_id: str | None = None
    user_ip: str | None = None
    mac: str | None = None
    vlan_id1: str | None = None
    vlan_id2: str | None = None
    theme: str | None = None
    referer_url: str | None = None


@dataclass(frozen=True)
class PortalSettings:
    base_url: str = DEFAULT_BASE_URL
    ac_id: str = '1'
    challenge_path: str = '/cgi-bin/get_challenge'
    auth_path: str = '/cgi-bin/srun_portal'
    callback_prefix: str = DEFAULT_CALLBACK_PREFIX
    n: str = DEFAULT_N
    type: str = DEFAULT_TYPE
    enc_ver: str = DEFAULT_ENC_VER
    user_agent: str = 'ecnu-network-keeper/1.0'

    @property
    def endpoint(self) -> str:
        return urljoin(self.base_url, self.auth_path)


class PortalDiscovery:
    def __init__(
        self,
        targets: tuple[str, ...] = DEFAULT_DISCOVERY_URLS,
        *,
        timeout: float = 5.0,
        opener: Callable[[Request, float], object] | None = None,
        request_factory: Callable[..., Request] = Request,
    ) -> None:
        self.targets = targets
        self.timeout = timeout
        self._opener = opener or self._default_open
        self._request_factory = request_factory

    def discover(self) -> PortalContext:
        for target in self.targets:
            context = self._probe_target(target)
            if context and (context.ac_id or context.user_ip or context.mac):
                return context
        return PortalContext()

    def _probe_target(self, url: str) -> PortalContext | None:
        request = self._request_factory(url=url)
        try:
            response = self._opener(request, self.timeout)
        except (HTTPError, URLError, OSError):
            return None

        try:
            body = response.read().decode('utf-8', errors='replace')
            final_url = response.geturl()
        finally:
            close = getattr(response, 'close', None)
            if callable(close):
                close()

        return extract_portal_context(final_url, body)

    @staticmethod
    def _default_open(request: Request, timeout: float) -> object:
        return urlopen(request, timeout=timeout)


class PortalClient:
    def __init__(
        self,
        settings: PortalSettings | None = None,
        *,
        discoverer: PortalDiscovery | None = None,
        opener: Callable[[Request, float], object] | None = None,
        request_factory: Callable[..., Request] = Request,
        timeout: float = 5.0,
        random_source: random.Random | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.settings = settings or PortalSettings()
        self.discoverer = discoverer or PortalDiscovery(timeout=timeout)
        self._opener = opener or self._default_open
        self._request_factory = request_factory
        self.timeout = timeout
        self._random = random_source or random.Random()
        self._clock = clock or time.time

    def submit(self, action: str, credentials: Credentials) -> str:
        context = self.discoverer.discover()
        if action == 'login':
            response = self._login(credentials, context)
        elif action == 'logout':
            response = self._logout(credentials, context)
        else:
            raise ValueError(f'Unsupported action: {action}')
        return json.dumps(response, ensure_ascii=False, sort_keys=True)

    def _login(self, credentials: Credentials, context: PortalContext) -> dict[str, object]:
        portal_username = credentials.portal_username
        ip_address = context.user_ip or ''
        challenge = self._send_jsonp_request(
            self.settings.challenge_path,
            {
                'username': portal_username,
                'ip': ip_address,
            },
            context,
        )
        token = str(challenge.get('challenge', '')).strip()
        if not token:
            raise ValueError('Portal challenge response did not include a usable token.')

        if not ip_address:
            ip_address = str(challenge.get('client_ip') or challenge.get('online_ip') or '').strip()

        ac_id = context.ac_id or self.settings.ac_id
        encoded_info = _encode_user_info(
            {
                'username': portal_username,
                'password': credentials.password,
                'ip': ip_address,
                'acid': ac_id,
                'enc_ver': self.settings.enc_ver,
            },
            token,
        )
        hashed_password = _hmac_md5(credentials.password, token)
        checksum = _build_checksum(
            token=token,
            username=portal_username,
            hmd5=hashed_password,
            ac_id=ac_id,
            ip=ip_address,
            n=self.settings.n,
            type_=self.settings.type,
            info=encoded_info,
        )
        response = self._send_jsonp_request(
            self.settings.auth_path,
            {
                'action': 'login',
                'username': portal_username,
                'password': '{MD5}' + hashed_password,
                'os': platform.system() or 'Linux',
                'name': platform.platform(aliased=True, terse=True) or platform.system() or 'Linux',
                'double_stack': '0',
                'chksum': checksum,
                'info': encoded_info,
                'ac_id': ac_id,
                'ip': ip_address,
                'n': self.settings.n,
                'type': self.settings.type,
            },
            context,
        )
        self._raise_if_rejected('login', response)
        return response

    def _logout(self, credentials: Credentials, context: PortalContext) -> dict[str, object]:
        portal_username = credentials.portal_username
        response = self._send_jsonp_request(
            self.settings.auth_path,
            {
                'action': 'logout',
                'username': portal_username,
                'ac_id': context.ac_id or self.settings.ac_id,
                'ip': context.user_ip or '',
            },
            context,
        )
        self._raise_if_rejected('logout', response)
        return response

    def _send_jsonp_request(
        self,
        path: str,
        params: dict[str, str],
        context: PortalContext,
    ) -> dict[str, object]:
        callback = self._build_callback_name()
        request_params = {key: value for key, value in params.items() if value is not None}
        request_params['callback'] = callback
        request_params['_'] = str(int(self._clock() * 1000))
        endpoint = urljoin(self._resolve_base_url(context), path)
        request_url = endpoint + '?' + urlencode(request_params, quote_via=quote_plus)
        headers = {
            'User-Agent': self.settings.user_agent,
        }
        if context.referer_url:
            headers['Referer'] = context.referer_url
        request = self._request_factory(url=request_url, headers=headers)
        try:
            response = self._opener(request, self.timeout)
        except HTTPError as exc:
            raise ValueError(
                f'Portal request failed with HTTP {exc.code} at {endpoint}. '
                'The campus portal endpoint may have changed.'
            ) from exc
        try:
            raw = response.read().decode('utf-8', errors='replace')
        finally:
            close = getattr(response, 'close', None)
            if callable(close):
                close()
        try:
            payload = _parse_jsonp_payload(raw)
        except ValueError as exc:
            raise ValueError(f'Portal returned an unexpected response from {endpoint}.') from exc
        if not isinstance(payload, dict):
            raise ValueError(f'Portal returned a non-object response from {endpoint}.')
        return payload

    def _resolve_base_url(self, context: PortalContext) -> str:
        if context.referer_url:
            parsed = urlparse(context.referer_url)
            if parsed.scheme and parsed.netloc:
                return f'{parsed.scheme}://{parsed.netloc}'
        return self.settings.base_url

    def _build_callback_name(self) -> str:
        return f'{self.settings.callback_prefix}_{int(self._clock() * 1000)}{self._random.randint(100, 999)}'

    @staticmethod
    def _default_open(request: Request, timeout: float) -> object:
        return urlopen(request, timeout=timeout)

    @staticmethod
    def _raise_if_rejected(action: str, response: dict[str, object]) -> None:
        if _response_is_success(response):
            return
        detail = _extract_response_detail(response)
        if detail:
            raise ValueError(f'Portal {action} was rejected: {detail}')
        raise ValueError(f'Portal {action} was rejected: {json.dumps(response, ensure_ascii=False, sort_keys=True)}')


def extract_portal_context(final_url: str | None, body: str) -> PortalContext:
    params: dict[str, str] = {}
    referer_url = final_url

    if final_url:
        params.update(_extract_query_params(final_url))

    meta_target = _extract_meta_refresh_target(final_url, body)
    if meta_target:
        referer_url = meta_target
        params.update(_extract_query_params(meta_target))

    return PortalContext(
        ac_id=params.get('ac_id'),
        user_ip=params.get('user_ip'),
        mac=params.get('mac'),
        vlan_id1=params.get('vlan_id1'),
        vlan_id2=params.get('vlan_id2'),
        theme=params.get('theme'),
        referer_url=referer_url,
    )


def _extract_query_params(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    values = parse_qs(parsed.query, keep_blank_values=True)
    return {key: items[-1] for key, items in values.items() if items}


def _extract_meta_refresh_target(base_url: str | None, body: str) -> str | None:
    match = META_REFRESH_RE.search(body)
    if not match:
        return None
    target = unescape(match.group(1)).strip()
    if not target:
        return None
    if base_url:
        return urljoin(base_url, target)
    return target


def _parse_jsonp_payload(raw: str) -> object:
    payload_text = raw.strip()
    if not payload_text:
        raise ValueError('Empty portal response.')
    if payload_text.startswith('{'):
        return json.loads(payload_text)
    match = JSONP_RE.match(payload_text)
    if not match:
        raise ValueError('Response is not valid JSONP.')
    return json.loads(match.group(2))


def _response_is_success(response: dict[str, object]) -> bool:
    error = str(response.get('error', '')).strip().lower()
    res = str(response.get('res', '')).strip().lower()
    ecode = str(response.get('ecode', '')).strip()
    if error and error not in {'ok'}:
        return False
    if res and res not in {'ok'}:
        return False
    if ecode and ecode not in {'0'}:
        return False
    return True


def _extract_response_detail(response: dict[str, object]) -> str:
    parts: list[str] = []
    for key in ('error_msg', 'ploy_msg', 'suc_msg', 'error', 'res', 'ecode'):
        value = str(response.get(key, '')).strip()
        if value and value.lower() not in {'ok'} and value not in {'0'} and value not in parts:
            parts.append(value)
    return ' | '.join(parts)


def _encode_user_info(info: dict[str, str], token: str) -> str:
    payload = json.dumps(info, ensure_ascii=False, separators=(',', ':'))
    encoded = _xencode(payload, token)
    return '{SRBX1}' + _srun_base64_encode(encoded.encode('latin1'))


def _hmac_md5(password: str, token: str) -> str:
    return hmac.new(token.encode('utf-8'), password.encode('utf-8'), hashlib.md5).hexdigest()


def _build_checksum(*, token: str, username: str, hmd5: str, ac_id: str, ip: str, n: str, type_: str, info: str) -> str:
    checksum_source = ''.join(
        [
            token,
            username,
            token,
            hmd5,
            token,
            ac_id,
            token,
            ip,
            token,
            n,
            token,
            type_,
            token,
            info,
        ]
    )
    return hashlib.sha1(checksum_source.encode('utf-8')).hexdigest()


def _srun_base64_encode(data: bytes) -> str:
    standard = base64.b64encode(data).decode('ascii')
    translation = str.maketrans(STD_BASE64_ALPHABET, SRUN_BASE64_ALPHABET)
    return standard.translate(translation)


def _xencode(message: str, key: str) -> str:
    if not message:
        return ''

    values = _string_to_int_array(message, include_length=True)
    keys = _string_to_int_array(key.ljust(4, '\x00'), include_length=False)
    if len(keys) < 4:
        keys.extend([0] * (4 - len(keys)))

    count = len(values) - 1
    z = values[count]
    y = values[0]
    total = 0
    delta = 0x9E3779B9
    rounds = 6 + 52 // (count + 1)

    while rounds > 0:
        rounds -= 1
        total = (total + delta) & 0xFFFFFFFF
        e = (total >> 2) & 3
        for index in range(count):
            y = values[index + 1]
            mixed = _xencode_mix(total, y, z, index, e, keys)
            values[index] = (values[index] + mixed) & 0xFFFFFFFF
            z = values[index]
        y = values[0]
        mixed = _xencode_mix(total, y, z, count, e, keys)
        values[count] = (values[count] + mixed) & 0xFFFFFFFF
        z = values[count]

    return _int_array_to_string(values, include_length=False)


def _xencode_mix(total: int, y: int, z: int, index: int, e: int, keys: list[int]) -> int:
    mixed = _unsigned_right_shift(z, 5) ^ (y << 2)
    mixed = (mixed + ((_unsigned_right_shift(y, 3) ^ (z << 4)) ^ (total ^ y))) & 0xFFFFFFFF
    mixed = (mixed + (keys[(index & 3) ^ e] ^ z)) & 0xFFFFFFFF
    return mixed


def _string_to_int_array(value: str, *, include_length: bool) -> list[int]:
    result: list[int] = []
    for index in range(0, len(value), 4):
        current = (
            _ord_at(value, index)
            | (_ord_at(value, index + 1) << 8)
            | (_ord_at(value, index + 2) << 16)
            | (_ord_at(value, index + 3) << 24)
        ) & 0xFFFFFFFF
        result.append(current)
    if include_length:
        result.append(len(value))
    return result


def _int_array_to_string(values: list[int], *, include_length: bool) -> str:
    chars: list[str] = []
    total_length = len(values) * 4
    if include_length:
        data_length = values[-1]
        if data_length < total_length - 3 or data_length > total_length:
            return ''
        total_length = data_length
    for value in values:
        chars.append(chr(value & 0xFF))
        chars.append(chr((_unsigned_right_shift(value, 8)) & 0xFF))
        chars.append(chr((_unsigned_right_shift(value, 16)) & 0xFF))
        chars.append(chr((_unsigned_right_shift(value, 24)) & 0xFF))
    return ''.join(chars)[:total_length]


def _ord_at(value: str, index: int) -> int:
    if index >= len(value):
        return 0
    return ord(value[index])


def _unsigned_right_shift(value: int, bits: int) -> int:
    return (value & 0xFFFFFFFF) >> bits




