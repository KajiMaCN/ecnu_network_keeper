import unittest

from ecnu_network_keeper.config import Credentials
from ecnu_network_keeper.service import AuthStatus, NetworkAuthService


class FakeConnectivityChecker:
    def __init__(self, states: list[bool]) -> None:
        self._states = list(states)

    def is_online(self, *, verbose: bool = False) -> bool:
        if not self._states:
            raise AssertionError('Connectivity state queue is empty.')
        return self._states.pop(0)


class FakePortalClient:
    def __init__(self, response_text: str = 'ok') -> None:
        self.response_text = response_text
        self.actions: list[tuple[str, Credentials]] = []

    def submit(self, action: str, credentials: Credentials) -> str:
        self.actions.append((action, credentials))
        return self.response_text


class NetworkAuthServiceTest(unittest.TestCase):
    def test_login_skips_when_already_online(self) -> None:
        portal = FakePortalClient()
        service = NetworkAuthService(
            portal_client=portal,
            connectivity_checker=FakeConnectivityChecker([True]),
        )

        result = service.login(Credentials(username='alice', password='secret'))

        self.assertEqual(result.status, AuthStatus.ALREADY_ONLINE)
        self.assertEqual(portal.actions, [])

    def test_login_reports_success_after_connectivity_recovers(self) -> None:
        portal = FakePortalClient('login-ok')
        service = NetworkAuthService(
            portal_client=portal,
            connectivity_checker=FakeConnectivityChecker([False, True]),
        )

        result = service.login(Credentials(username='alice', password='secret'))

        self.assertEqual(result.status, AuthStatus.LOGIN_SUCCESS)
        self.assertEqual(len(portal.actions), 1)
        self.assertEqual(portal.actions[0][0], 'login')

    def test_logout_reports_success_after_connectivity_drops(self) -> None:
        portal = FakePortalClient('logout-ok')
        service = NetworkAuthService(
            portal_client=portal,
            connectivity_checker=FakeConnectivityChecker([True, False]),
        )

        result = service.logout(Credentials(username='alice', password='secret'))

        self.assertEqual(result.status, AuthStatus.LOGOUT_SUCCESS)
        self.assertEqual(len(portal.actions), 1)
        self.assertEqual(portal.actions[0][0], 'logout')

    def test_logout_skips_when_already_offline(self) -> None:
        portal = FakePortalClient()
        service = NetworkAuthService(
            portal_client=portal,
            connectivity_checker=FakeConnectivityChecker([False]),
        )

        result = service.logout(Credentials(username='alice', password='secret'))

        self.assertEqual(result.status, AuthStatus.ALREADY_OFFLINE)
        self.assertEqual(portal.actions, [])

    def test_login_retries_connectivity_check_after_request(self) -> None:
        portal = FakePortalClient('login-ok')
        sleep_calls: list[float] = []
        service = NetworkAuthService(
            portal_client=portal,
            connectivity_checker=FakeConnectivityChecker([False, False, False, True]),
            verify_attempts=3,
            verify_delay=0.5,
            sleep_fn=sleep_calls.append,
        )

        result = service.login(Credentials(username='alice', password='secret'))

        self.assertEqual(result.status, AuthStatus.LOGIN_SUCCESS)
        self.assertEqual(sleep_calls, [0.5, 0.5])


if __name__ == '__main__':
    unittest.main()
