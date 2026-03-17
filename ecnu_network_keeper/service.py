from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import time
from typing import Callable

from .config import Credentials
from .connectivity import ConnectivityChecker
from .portal import PortalClient


class AuthStatus(str, Enum):
    ALREADY_ONLINE = 'already_online'
    ALREADY_OFFLINE = 'already_offline'
    LOGIN_SUCCESS = 'login_success'
    LOGIN_FAILED = 'login_failed'
    LOGOUT_SUCCESS = 'logout_success'
    LOGOUT_FAILED = 'logout_failed'


@dataclass(frozen=True)
class AuthResult:
    action: str
    status: AuthStatus
    online: bool
    message: str
    response_text: str | None = None


class NetworkAuthService:
    def __init__(
        self,
        portal_client: PortalClient | None = None,
        connectivity_checker: ConnectivityChecker | None = None,
        *,
        verify_attempts: int = 3,
        verify_delay: float = 2.0,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.portal_client = portal_client or PortalClient()
        self.connectivity_checker = connectivity_checker or ConnectivityChecker()
        self.verify_attempts = verify_attempts
        self.verify_delay = verify_delay
        self._sleep_fn = sleep_fn

    def login(self, credentials: Credentials, *, verbose: bool = False) -> AuthResult:
        online_before = self.connectivity_checker.is_online(verbose=verbose)
        if online_before:
            return AuthResult(
                action='login',
                status=AuthStatus.ALREADY_ONLINE,
                online=True,
                message='Internet is already connected.',
            )

        response_text = self.portal_client.submit('login', credentials)
        accepted_message = _build_portal_response_summary('login', response_text)
        online_after = self._wait_for_connectivity(target_online=True, verbose=verbose)
        if online_after:
            return AuthResult(
                action='login',
                status=AuthStatus.LOGIN_SUCCESS,
                online=True,
                message=accepted_message or 'Login succeeded.',
                response_text=response_text,
            )

        return AuthResult(
            action='login',
            status=AuthStatus.LOGIN_FAILED,
            online=False,
            message=(
                f'{accepted_message} Connectivity check still failed.'
                if accepted_message
                else 'Login request was sent, but connectivity check still failed.'
            ),
            response_text=response_text,
        )

    def logout(self, credentials: Credentials, *, verbose: bool = False) -> AuthResult:
        online_before = self.connectivity_checker.is_online(verbose=verbose)
        if not online_before:
            return AuthResult(
                action='logout',
                status=AuthStatus.ALREADY_OFFLINE,
                online=False,
                message='Internet is already disconnected.',
            )

        response_text = self.portal_client.submit('logout', credentials)
        accepted_message = _build_portal_response_summary('logout', response_text)
        online_after = self._wait_for_connectivity(target_online=False, verbose=verbose)
        if not online_after:
            return AuthResult(
                action='logout',
                status=AuthStatus.LOGOUT_SUCCESS,
                online=False,
                message=accepted_message or 'Logout succeeded.',
                response_text=response_text,
            )

        return AuthResult(
            action='logout',
            status=AuthStatus.LOGOUT_FAILED,
            online=True,
            message=(
                f'{accepted_message} The network still looks online.'
                if accepted_message
                else 'Logout request was sent, but the network still looks online.'
            ),
            response_text=response_text,
        )

    def _wait_for_connectivity(self, *, target_online: bool, verbose: bool) -> bool:
        attempts = max(1, self.verify_attempts)
        is_online = False
        for attempt in range(attempts):
            is_online = self.connectivity_checker.is_online(verbose=verbose)
            if is_online == target_online:
                return is_online
            if attempt < attempts - 1 and self.verify_delay > 0:
                self._sleep_fn(self.verify_delay)
        return is_online


def _build_portal_response_summary(action: str, response_text: str | None) -> str | None:
    if not response_text:
        return None

    try:
        payload = json.loads(response_text)
    except (TypeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None

    detail = str(payload.get('ploy_msg') or payload.get('suc_msg') or '').strip()
    username = str(payload.get('username') or '').strip()
    ip_address = str(payload.get('online_ip') or payload.get('client_ip') or '').strip()

    parts: list[str] = []
    if detail:
        parts.append(detail)
    if username:
        parts.append(f'user={username}')
    if ip_address:
        parts.append(f'ip={ip_address}')

    if not parts:
        return None

    action_word = 'Login' if action == 'login' else 'Logout'
    return f'{action_word} succeeded. ' + ' | '.join(parts)
