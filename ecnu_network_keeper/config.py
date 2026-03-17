from __future__ import annotations

import base64
import binascii
import configparser
import hashlib
import hmac
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


CONFIG_PATH_ENV_VAR = 'ECNU_NET_CONFIG'
KEY_PATH_ENV_VAR = 'ECNU_NET_KEY_PATH'
SECRET_KEY_ENV_VAR = 'ECNU_NET_SECRET_KEY'
USERNAME_ENV_VAR = 'ECNU_NET_USERNAME'
PASSWORD_ENV_VAR = 'ECNU_NET_PASSWORD'
DOMAIN_ENV_VAR = 'ECNU_NET_DOMAIN'
DEFAULT_DOMAIN = '@stu.ecnu.edu.cn'
CONFIG_VERSION = '4'
TOKEN_PREFIX = 'nk1$'
NONCE_SIZE = 16
TAG_SIZE = 32
KEY_SIZE = 32


def _default_config_path() -> Path:
    configured_path = os.environ.get(CONFIG_PATH_ENV_VAR, '').strip()
    if configured_path:
        return Path(configured_path).expanduser()
    return Path.home() / '.config' / 'ecnu_network_keeper' / 'config.ini'


def _default_key_path(config_path: Path | None = None) -> Path:
    configured_path = os.environ.get(KEY_PATH_ENV_VAR, '').strip()
    if configured_path:
        return Path(configured_path).expanduser()

    target = config_path or DEFAULT_CONFIG_PATH
    return target.with_name(f'{target.stem}.key')


DEFAULT_CONFIG_PATH = _default_config_path()
DEFAULT_KEY_PATH = _default_key_path(DEFAULT_CONFIG_PATH)


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str
    domain: str = DEFAULT_DOMAIN

    @property
    def portal_username(self) -> str:
        return self.username + self.domain


def normalize_domain(domain: str | None) -> str:
    if domain is None:
        return DEFAULT_DOMAIN
    value = domain.strip()
    if not value or value == '@undefined':
        return DEFAULT_DOMAIN
    if value.startswith('@'):
        return value
    if '@' in value:
        suffix = value.split('@', 1)[1].strip()
        return '@' + suffix if suffix else ''
    return '@' + value


def _urlsafe_b64decode(value: str) -> bytes:
    padding = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode('ascii'))


def generate_secret_key() -> bytes:
    return base64.urlsafe_b64encode(secrets.token_bytes(KEY_SIZE))


class CredentialCipher:
    def __init__(self, secret_key: bytes) -> None:
        self._enc_key = hashlib.sha256(secret_key + b':enc').digest()
        self._mac_key = hashlib.sha256(secret_key + b':mac').digest()

    def encrypt(self, value: str) -> str:
        plaintext = value.encode('utf-8')
        nonce = secrets.token_bytes(NONCE_SIZE)
        ciphertext = _xor_bytes(plaintext, _keystream(self._enc_key, nonce, len(plaintext)))
        tag = hmac.new(self._mac_key, nonce + ciphertext, hashlib.sha256).digest()
        payload = nonce + ciphertext + tag
        return TOKEN_PREFIX + base64.urlsafe_b64encode(payload).decode('ascii')

    def decrypt(self, token: str) -> str:
        if not token.startswith(TOKEN_PREFIX):
            raise ValueError('Stored credentials use an unsupported token format.')

        try:
            payload = _urlsafe_b64decode(token[len(TOKEN_PREFIX):])
        except (ValueError, binascii.Error) as exc:
            raise ValueError('Stored credentials are not valid encrypted data.') from exc

        if len(payload) < NONCE_SIZE + TAG_SIZE:
            raise ValueError('Stored credentials are incomplete or corrupted.')

        nonce = payload[:NONCE_SIZE]
        ciphertext = payload[NONCE_SIZE:-TAG_SIZE]
        tag = payload[-TAG_SIZE:]
        expected_tag = hmac.new(self._mac_key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            raise ValueError('Stored credentials could not be decrypted with the available key.')

        plaintext = _xor_bytes(ciphertext, _keystream(self._enc_key, nonce, len(ciphertext)))
        try:
            return plaintext.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise ValueError('Stored credentials are corrupted.') from exc


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        counter_bytes = counter.to_bytes(4, 'big')
        stream.extend(hmac.new(key, nonce + counter_bytes, hashlib.sha256).digest())
        counter += 1
    return bytes(stream[:length])


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def _normalize_secret_key(secret_key: str | bytes) -> bytes:
    try:
        key_text = secret_key.decode('ascii') if isinstance(secret_key, bytes) else secret_key
        decoded = _urlsafe_b64decode(key_text.strip())
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError(
            f'{SECRET_KEY_ENV_VAR} must be a valid urlsafe base64 key.'
        ) from exc

    if len(decoded) < KEY_SIZE:
        raise ValueError(f'{SECRET_KEY_ENV_VAR} must decode to at least {KEY_SIZE} bytes.')
    return decoded[:KEY_SIZE]


def _set_private_permissions(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_credentials_from_env(env: Mapping[str, str] | None = None) -> Credentials | None:
    source = os.environ if env is None else env
    username = source.get(USERNAME_ENV_VAR, '').strip()
    password = source.get(PASSWORD_ENV_VAR, '')
    raw_domain = source.get(DOMAIN_ENV_VAR, '')

    if not username and not password and not raw_domain.strip():
        return None
    if not username or not password:
        raise ValueError(
            f'{USERNAME_ENV_VAR} and {PASSWORD_ENV_VAR} must be provided together.'
        )

    return Credentials(username=username, password=password, domain=normalize_domain(raw_domain))


class CredentialsRepository:
    def __init__(
        self,
        path: Path | None = None,
        *,
        key_path: Path | None = None,
        secret_key: str | bytes | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.path = path or DEFAULT_CONFIG_PATH
        self.key_path = key_path or _default_key_path(self.path)
        self._secret_key = secret_key
        self._env = os.environ if env is None else env

    def load(self) -> Credentials | None:
        parser = configparser.ConfigParser()
        files = parser.read(self.path, encoding='utf-8')
        if not files or 'user' not in parser:
            return None

        section = parser['user']
        if 'username_encrypted' in section:
            cipher = self._get_cipher(allow_create=False)
            if cipher is None:
                raise ValueError(
                    'Encrypted credentials were found, but no decryption key is available. '
                    f'Set {SECRET_KEY_ENV_VAR} or provide the key file at {self.key_path}.'
                )

            username = cipher.decrypt(section.get('username_encrypted', ''))
            password_token = section.get('password_encrypted', '')
            password = cipher.decrypt(password_token) if password_token else ''
            domain_token = section.get('domain_encrypted', '')
            domain = normalize_domain(cipher.decrypt(domain_token)) if domain_token else DEFAULT_DOMAIN
            return Credentials(username=username, password=password, domain=domain)

        username = section.get('username', '').strip()
        if not username:
            return None

        password = section.get('password', '')
        domain = normalize_domain(section.get('domain', DEFAULT_DOMAIN))
        return Credentials(username=username, password=password, domain=domain)

    def save(self, credentials: Credentials, *, save_password: bool) -> None:
        cipher = self._get_cipher(allow_create=True)
        if cipher is None:
            raise ValueError('Unable to initialize credential encryption.')

        parser = configparser.ConfigParser()
        parser['user'] = {
            'version': CONFIG_VERSION,
            'username_encrypted': cipher.encrypt(credentials.username),
        }
        if save_password:
            parser['user']['password_encrypted'] = cipher.encrypt(credentials.password)
        if credentials.domain:
            parser['user']['domain_encrypted'] = cipher.encrypt(normalize_domain(credentials.domain))

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('w', encoding='utf-8') as handle:
            parser.write(handle)
        _set_private_permissions(self.path)

    def _get_cipher(self, *, allow_create: bool) -> CredentialCipher | None:
        secret_key = self._resolve_secret_key(allow_create=allow_create)
        if secret_key is None:
            return None
        return CredentialCipher(secret_key)

    def _resolve_secret_key(self, *, allow_create: bool) -> bytes | None:
        if self._secret_key is not None:
            return _normalize_secret_key(self._secret_key)

        configured_key = self._env.get(SECRET_KEY_ENV_VAR, '').strip()
        if configured_key:
            return _normalize_secret_key(configured_key)

        if self.key_path.exists():
            return _normalize_secret_key(self.key_path.read_bytes().strip())

        if not allow_create:
            return None

        generated_key = generate_secret_key()
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        self.key_path.write_bytes(generated_key + b'\n')
        _set_private_permissions(self.key_path)
        return _normalize_secret_key(generated_key)




