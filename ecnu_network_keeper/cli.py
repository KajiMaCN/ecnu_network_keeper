from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import datetime
from getpass import getpass
import os
from pathlib import Path
import sys
import time
from typing import Callable

from .config import DEFAULT_DOMAIN, Credentials, CredentialsRepository, load_credentials_from_env, normalize_domain
from .service import AuthStatus, NetworkAuthService
from .tracking import ConnectivityEventRecorder


KEEPER_INTERVAL_ENV_VAR = 'ECNU_KEEPER_INTERVAL'


@dataclass(frozen=True)
class CredentialSelection:
    credentials: Credentials | None
    source: str | None = None


def _env_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name, '').strip()
    if not raw_value:
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ValueError(f'{name} must be a number, got {raw_value!r}.') from exc


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description='ECNU network login/logout tool')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--login', action='store_true', help='Login to the ECNU network portal')
    group.add_argument('--logout', action='store_true', help='Logout from the ECNU network portal')
    group.add_argument('--update', action='store_true', help='Update saved credentials')
    parser.add_argument('--daemon', action='store_true', help='Keep running and retry the selected action')
    parser.add_argument(
        '--interval',
        type=float,
        default=_env_float(KEEPER_INTERVAL_ENV_VAR, 120.0),
        help='Seconds between daemon retries',
    )
    parser.add_argument(
        '--config',
        type=Path,
        default=None,
        help='Path to the local credential config file',
    )
    parser.add_argument('--username', default=None, help='Student ID used for login')
    parser.add_argument('--password', default=None, help='Password used for login')
    parser.add_argument('--domain', default=None, help='Login domain suffix, defaults to @stu.ecnu.edu.cn')
    parser.add_argument(
        '--store-password',
        action='store_true',
        help='Store credentials in encrypted form in the config file',
    )
    parser.add_argument('--verbose', action='store_true', help='Print connectivity checks and raw portal responses')
    return parser


def prompt_for_credentials(existing: Credentials | None = None, *, require_password: bool = True) -> Credentials:
    default_username = existing.username if existing else ''
    if default_username:
        username = input(f'Student ID [{default_username}]: ').strip() or default_username
    else:
        username = input('Student ID: ').strip()

    if not username:
        raise ValueError('Student ID is required.')

    default_domain = existing.domain if existing else DEFAULT_DOMAIN
    if default_domain:
        domain = input(f'Domain suffix [{default_domain}]: ').strip() or default_domain
    else:
        domain = input(f'Domain suffix [{DEFAULT_DOMAIN}]: ').strip()
    domain = normalize_domain(domain)

    password = getpass('Password: ')
    if not password and existing and existing.password:
        password = existing.password

    if require_password and not password:
        raise ValueError('Password is required.')

    return Credentials(username=username, password=password, domain=domain)


def _override_domain(credentials: Credentials, domain: str | None) -> Credentials:
    if domain is None:
        return credentials
    return Credentials(username=credentials.username, password=credentials.password, domain=normalize_domain(domain))


def select_credentials(
    repository: CredentialsRepository,
    *,
    username: str | None = None,
    password: str | None = None,
    domain: str | None = None,
    allow_prompt: bool,
    require_password: bool = True,
) -> CredentialSelection:
    if bool(username) != bool(password):
        raise ValueError('Both --username and --password must be provided together.')
    if username and password:
        return CredentialSelection(
            Credentials(username=username, password=password, domain=normalize_domain(domain)),
            'args',
        )

    try:
        env_credentials = load_credentials_from_env()
    except ValueError:
        if allow_prompt and sys.stdin.isatty():
            env_credentials = None
        else:
            raise
    if env_credentials is not None:
        return CredentialSelection(_override_domain(env_credentials, domain), 'env')

    saved = repository.load()
    if saved and (saved.password or not require_password):
        return CredentialSelection(_override_domain(saved, domain), 'config')

    if allow_prompt and sys.stdin.isatty():
        prompted = prompt_for_credentials(
            _override_domain(saved, domain) if saved else None,
            require_password=require_password,
        )
        return CredentialSelection(prompted, 'prompt')

    return CredentialSelection(None, None)


def maybe_persist_credentials(
    selection: CredentialSelection,
    repository: CredentialsRepository,
    *,
    save_password: bool,
) -> bool:
    if selection.credentials is None or selection.source is None:
        return False

    if selection.source == 'prompt':
        repository.save(selection.credentials, save_password=save_password)
        return True

    if save_password and selection.source in {'args', 'env'}:
        repository.save(selection.credentials, save_password=True)
        return True

    return False


def _timestamped(message: str) -> str:
    return f'[{datetime.now().replace(microsecond=0).isoformat()}] {message}'


def run_daemon(
    args,
    repository: CredentialsRepository,
    service: NetworkAuthService | None = None,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
    iterations: int | None = None,
) -> int:
    if args.update:
        raise ValueError('--update cannot be used with --daemon.')
    if args.interval <= 0:
        raise ValueError('--interval must be greater than 0.')

    service = service or NetworkAuthService()
    recorder = ConnectivityEventRecorder.from_config_path(repository.path)
    action = service.login if args.login else service.logout
    last_message: str | None = None
    persisted_external_credentials = False
    current_iteration = 0

    while iterations is None or current_iteration < iterations:
        current_iteration += 1
        response_text: str | None = None
        observed_online: bool | None = None
        try:
            selection = select_credentials(
                repository,
                username=args.username,
                password=args.password,
                domain=args.domain,
                allow_prompt=False,
                require_password=args.login,
            )

            if selection.credentials is None:
                observed_online = service.connectivity_checker.is_online(verbose=False)
                message = (
                    'Credentials are not available yet. '
                    'Set ECNU_NET_USERNAME/ECNU_NET_PASSWORD or run --update in the container.'
                )
            else:
                if args.store_password and not persisted_external_credentials:
                    persisted_external_credentials = maybe_persist_credentials(
                        selection,
                        repository,
                        save_password=True,
                    )
                result = action(selection.credentials, verbose=args.verbose)
                observed_online = result.online
                message = result.message
                response_text = result.response_text
        except Exception as exc:
            message = f'Daemon loop failed: {exc}'

        if observed_online is not None:
            recorder.record(observed_online)

        if args.verbose or message != last_message:
            print(_timestamped(message))
            last_message = message

        if args.verbose and response_text:
            print(response_text)

        if iterations is not None and current_iteration >= iterations:
            break

        sleep_fn(args.interval)

    return 0


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = CredentialsRepository(args.config)
    if args.daemon:
        return run_daemon(args, repository)

    if args.update:
        selection = select_credentials(
            repository,
            username=args.username,
            password=args.password,
            domain=args.domain,
            allow_prompt=True,
            require_password=not args.logout,
        )
        if selection.credentials is None:
            raise ValueError('Credentials are required for --update.')
        repository.save(selection.credentials, save_password=args.store_password)
        print(f'Updated credentials at {repository.path}')
        return 0

    selection = select_credentials(
        repository,
        username=args.username,
        password=args.password,
        domain=args.domain,
        allow_prompt=True,
        require_password=not args.logout,
    )
    if selection.credentials is None:
        raise ValueError(
            'Credentials are required. Provide --username/--password, set environment variables, '
            'use a saved config, or run the command interactively.'
        )

    service = NetworkAuthService()
    maybe_persist_credentials(selection, repository, save_password=args.store_password)
    action = service.login if args.login else service.logout
    result = action(selection.credentials, verbose=args.verbose)
    print(result.message)

    if args.verbose and result.response_text:
        print(result.response_text)

    if result.status in {AuthStatus.LOGIN_FAILED, AuthStatus.LOGOUT_FAILED}:
        return 1
    return 0


def main() -> None:
    try:
        code = run()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        code = 2
    raise SystemExit(code)
