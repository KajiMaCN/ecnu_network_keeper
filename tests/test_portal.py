from urllib.error import HTTPError
import random
import unittest

from ecnu_network_keeper.config import Credentials
from ecnu_network_keeper.portal import PortalClient, PortalContext, PortalSettings, extract_portal_context


class FakeResponse:
    def __init__(self, payload: bytes, url: str = 'https://login.ecnu.edu.cn/index_1.html') -> None:
        self.payload = payload
        self.url = url

    def read(self) -> bytes:
        return self.payload

    def geturl(self) -> str:
        return self.url

    def close(self) -> None:
        return None


class FakeDiscoverer:
    def __init__(self, context: PortalContext) -> None:
        self.context = context
        self.calls = 0

    def discover(self) -> PortalContext:
        self.calls += 1
        return self.context


class PortalClientTest(unittest.TestCase):
    def test_submit_uses_srun_challenge_flow(self) -> None:
        requests = []

        def opener(request, timeout):
            requests.append(request)
            if '/cgi-bin/get_challenge?' in request.full_url:
                return FakeResponse(
                    b'jQuery1124_1({"challenge":"token123","client_ip":"172.23.138.28","error":"ok","ecode":0})',
                    url=request.full_url,
                )
            if '/cgi-bin/srun_portal?' in request.full_url:
                return FakeResponse(
                    b'jQuery1124_2({"error":"ok","res":"ok","suc_msg":"login_ok"})',
                    url=request.full_url,
                )
            raise AssertionError(f'unexpected URL: {request.full_url}')

        discoverer = FakeDiscoverer(
            PortalContext(
                ac_id='1',
                user_ip='172.23.138.28',
                mac='04:a9:59:9b:20:02',
                vlan_id1='0',
                vlan_id2='0',
                referer_url='https://login.ecnu.edu.cn/srun_portal_pc?ac_id=1',
            )
        )
        client = PortalClient(
            opener=opener,
            discoverer=discoverer,
            random_source=random.Random(1),
            clock=lambda: 1700000000.0,
        )

        result = client.submit('login', Credentials(username='alice', password='secret', domain='@cmcc'))

        self.assertIn('login_ok', result)
        self.assertEqual(len(requests), 2)
        self.assertIn('/cgi-bin/get_challenge?', requests[0].full_url)
        self.assertIn('username=alice%40cmcc', requests[0].full_url)
        self.assertIn('ip=172.23.138.28', requests[0].full_url)
        self.assertEqual(requests[0].headers.get('Referer'), 'https://login.ecnu.edu.cn/srun_portal_pc?ac_id=1')

        self.assertIn('/cgi-bin/srun_portal?', requests[1].full_url)
        self.assertIn('action=login', requests[1].full_url)
        self.assertIn('username=alice%40cmcc', requests[1].full_url)
        self.assertIn('ac_id=1', requests[1].full_url)
        self.assertIn('ip=172.23.138.28', requests[1].full_url)
        self.assertIn('password=%7BMD5%7D', requests[1].full_url)
        self.assertIn('chksum=', requests[1].full_url)
        self.assertIn('info=%7BSRBX1%7D', requests[1].full_url)
        self.assertEqual(discoverer.calls, 1)

    def test_logout_uses_srun_portal(self) -> None:
        requests = []

        def opener(request, timeout):
            requests.append(request)
            return FakeResponse(
                b'jQuery1124_2({"error":"ok","res":"ok","suc_msg":"logout_ok"})',
                url=request.full_url,
            )

        client = PortalClient(
            opener=opener,
            discoverer=FakeDiscoverer(PortalContext(ac_id='1', user_ip='172.23.138.28')),
            random_source=random.Random(1),
            clock=lambda: 1700000000.0,
        )

        result = client.submit('logout', Credentials(username='alice', password='secret', domain='@cmcc'))

        self.assertIn('logout_ok', result)
        self.assertEqual(len(requests), 1)
        self.assertIn('/cgi-bin/srun_portal?', requests[0].full_url)
        self.assertIn('action=logout', requests[0].full_url)
        self.assertIn('username=alice%40cmcc', requests[0].full_url)
        self.assertIn('ip=172.23.138.28', requests[0].full_url)

    def test_submit_wraps_http_error_with_readable_message(self) -> None:
        def opener(request, timeout):
            raise HTTPError(request.full_url, 404, 'Not Found', hdrs=None, fp=None)

        client = PortalClient(
            opener=opener,
            settings=PortalSettings(),
            discoverer=FakeDiscoverer(PortalContext()),
            random_source=random.Random(1),
            clock=lambda: 1700000000.0,
        )

        with self.assertRaises(ValueError) as context:
            client.submit('login', Credentials(username='alice', password='secret'))

        self.assertIn('HTTP 404', str(context.exception))
        self.assertIn('/cgi-bin/get_challenge', str(context.exception))

    def test_submit_raises_when_portal_rejects_login(self) -> None:
        def opener(request, timeout):
            if '/cgi-bin/get_challenge?' in request.full_url:
                return FakeResponse(
                    b'jQuery1124_1({"challenge":"token123","client_ip":"172.23.138.28","error":"ok","ecode":0})',
                    url=request.full_url,
                )
            return FakeResponse(
                b'jQuery1124_2({"error":"E2901","error_msg":"password_error","res":"fail"})',
                url=request.full_url,
            )

        client = PortalClient(
            opener=opener,
            discoverer=FakeDiscoverer(PortalContext(ac_id='1', user_ip='172.23.138.28')),
            random_source=random.Random(1),
            clock=lambda: 1700000000.0,
        )

        with self.assertRaises(ValueError) as context:
            client.submit('login', Credentials(username='alice', password='secret', domain='@cmcc'))

        self.assertIn('password_error', str(context.exception))

    def test_extract_portal_context_from_meta_refresh(self) -> None:
        context = extract_portal_context(
            'https://login.ecnu.edu.cn/index_1.html?vlan_id1=0&vlan_id2=0&mac=04:a9:59:9b:20:02&user_ip=172.23.138.28',
            '<meta http-equiv="refresh" content="0;url=/srun_portal_pc?ac_id=1&amp;mac=04%3Aa9%3A59%3A9b%3A20%3A02&amp;theme=pro&amp;user_ip=172.23.138.28&amp;vlan_id1=0&amp;vlan_id2=0">',
        )

        self.assertEqual(context.ac_id, '1')
        self.assertEqual(context.user_ip, '172.23.138.28')
        self.assertEqual(context.mac, '04:a9:59:9b:20:02')
        self.assertEqual(context.theme, 'pro')
        self.assertEqual(context.referer_url, 'https://login.ecnu.edu.cn/srun_portal_pc?ac_id=1&mac=04%3Aa9%3A59%3A9b%3A20%3A02&theme=pro&user_ip=172.23.138.28&vlan_id1=0&vlan_id2=0')


if __name__ == '__main__':
    unittest.main()
