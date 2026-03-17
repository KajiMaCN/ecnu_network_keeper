import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ecnu_network_keeper.cli import run_daemon, select_credentials
from ecnu_network_keeper.config import Credentials
from ecnu_network_keeper.service import AuthResult, AuthStatus


class FakeRepository:
    def __init__(self, credentials: Credentials | None = None) -> None:
        self.credentials = credentials
        self.saved: list[tuple[Credentials, bool]] = []
        self.path = Path('dummy.ini')

    def load(self) -> Credentials | None:
        return self.credentials

    def save(self, credentials: Credentials, *, save_password: bool) -> None:
        self.saved.append((credentials, save_password))
        password = credentials.password if save_password else ''
        self.credentials = Credentials(username=credentials.username, password=password, domain=credentials.domain)


class FakeConnectivityChecker:
    def __init__(self, online: bool = False) -> None:
        self.online = online

    def is_online(self, *, verbose: bool = False) -> bool:
        return self.online


class FakeService:
    def __init__(self, result: AuthResult, *, online: bool = False) -> None:
        self.result = result
        self.calls: list[tuple[str, Credentials, bool]] = []
        self.connectivity_checker = FakeConnectivityChecker(online)

    def login(self, credentials: Credentials, *, verbose: bool = False) -> AuthResult:
        self.calls.append(('login', credentials, verbose))
        return self.result

    def logout(self, credentials: Credentials, *, verbose: bool = False) -> AuthResult:
        self.calls.append(('logout', credentials, verbose))
        return self.result


class CliCredentialSelectionTest(unittest.TestCase):
    def test_select_credentials_prefers_environment(self) -> None:
        repository = FakeRepository(Credentials(username='saved', password='saved-pass', domain='@saved'))
        env = {
            'ECNU_NET_USERNAME': 'env-user',
            'ECNU_NET_PASSWORD': 'env-pass',
            'ECNU_NET_DOMAIN': 'cmcc',
        }

        with patch.dict(os.environ, env, clear=False):
            selection = select_credentials(repository, allow_prompt=False)

        self.assertEqual(selection.source, 'env')
        self.assertEqual(selection.credentials, Credentials(username='env-user', password='env-pass', domain='@cmcc'))

    def test_select_credentials_uses_config_when_environment_is_missing(self) -> None:
        repository = FakeRepository(Credentials(username='saved', password='saved-pass', domain='@saved'))

        with patch.dict(os.environ, {}, clear=True):
            selection = select_credentials(repository, allow_prompt=False)

        self.assertEqual(selection.source, 'config')
        self.assertEqual(selection.credentials, Credentials(username='saved', password='saved-pass', domain='@saved'))

    def test_select_credentials_can_override_domain(self) -> None:
        repository = FakeRepository(Credentials(username='saved', password='saved-pass', domain='@saved'))

        with patch.dict(os.environ, {}, clear=True):
            selection = select_credentials(repository, domain='cmcc', allow_prompt=False)

        self.assertEqual(selection.credentials, Credentials(username='saved', password='saved-pass', domain='@cmcc'))

    def test_select_credentials_allows_passwordless_config_for_logout(self) -> None:
        repository = FakeRepository(Credentials(username='saved', password='', domain='@saved'))

        with patch.dict(os.environ, {}, clear=True):
            selection = select_credentials(repository, allow_prompt=False, require_password=False)

        self.assertEqual(selection.source, 'config')
        self.assertEqual(selection.credentials, Credentials(username='saved', password='', domain='@saved'))

class CliDaemonTest(unittest.TestCase):
    def test_daemon_waits_when_credentials_are_missing(self) -> None:
        repository = FakeRepository()
        service = FakeService(
            AuthResult(
                action='login',
                status=AuthStatus.LOGIN_SUCCESS,
                online=True,
                message='Login succeeded.',
            ),
            online=False,
        )
        args = SimpleNamespace(
            login=True,
            logout=False,
            update=False,
            interval=1.0,
            username=None,
            password=None,
            domain=None,
            store_password=False,
            verbose=False,
        )

        with patch.dict(os.environ, {}, clear=True):
            exit_code = run_daemon(args, repository, service, iterations=1)

        self.assertEqual(exit_code, 0)
        self.assertEqual(service.calls, [])

    def test_daemon_logs_in_and_persists_environment_credentials(self) -> None:
        repository = FakeRepository()
        service = FakeService(
            AuthResult(
                action='login',
                status=AuthStatus.LOGIN_SUCCESS,
                online=True,
                message='Login succeeded.',
            )
        )
        args = SimpleNamespace(
            login=True,
            logout=False,
            update=False,
            interval=1.0,
            username=None,
            password=None,
            domain=None,
            store_password=True,
            verbose=False,
        )

        with patch.dict(
            os.environ,
            {
                'ECNU_NET_USERNAME': 'env-user',
                'ECNU_NET_PASSWORD': 'env-pass',
                'ECNU_NET_DOMAIN': 'cmcc',
            },
            clear=True,
        ):
            exit_code = run_daemon(args, repository, service, iterations=1)

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            service.calls,
            [('login', Credentials(username='env-user', password='env-pass', domain='@cmcc'), False)],
        )
        self.assertEqual(
            repository.saved,
            [(Credentials(username='env-user', password='env-pass', domain='@cmcc'), True)],
        )


if __name__ == '__main__':
    unittest.main()

