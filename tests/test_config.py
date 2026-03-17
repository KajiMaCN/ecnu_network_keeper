from pathlib import Path
import unittest

from ecnu_network_keeper.config import (
    Credentials,
    CredentialsRepository,
    DEFAULT_DOMAIN,
    generate_secret_key,
    load_credentials_from_env,
    normalize_domain,
)


class CredentialsRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path.cwd() / 'tests' / '_tmp_config.ini'
        self.key_path = Path.cwd() / 'tests' / '_tmp_config.key'
        for target in (self.path, self.key_path):
            if target.exists():
                target.unlink()

    def tearDown(self) -> None:
        for target in (self.path, self.key_path):
            if target.exists():
                target.unlink()

    def test_save_and_load_with_password(self) -> None:
        repository = CredentialsRepository(self.path, key_path=self.key_path)
        repository.save(Credentials(username='alice', password='secret', domain='@cmcc'), save_password=True)

        loaded = repository.load()
        content = self.path.read_text(encoding='utf-8')

        self.assertEqual(loaded, Credentials(username='alice', password='secret', domain='@cmcc'))
        self.assertNotIn('alice', content)
        self.assertNotIn('secret', content)
        self.assertNotIn('@cmcc', content)
        self.assertTrue(self.key_path.exists())

    def test_save_without_password(self) -> None:
        repository = CredentialsRepository(self.path, key_path=self.key_path)
        repository.save(Credentials(username='alice', password='secret', domain='@cmcc'), save_password=False)

        loaded = repository.load()
        content = self.path.read_text(encoding='utf-8')

        self.assertEqual(loaded, Credentials(username='alice', password='', domain='@cmcc'))
        self.assertNotIn('alice', content)
        self.assertNotIn('secret', content)
        self.assertNotIn('@cmcc', content)

    def test_repository_can_use_explicit_secret_key(self) -> None:
        secret_key = generate_secret_key().decode('ascii')
        repository = CredentialsRepository(self.path, key_path=self.key_path, secret_key=secret_key)
        repository.save(Credentials(username='alice', password='secret', domain='@cmcc'), save_password=True)

        reloaded = CredentialsRepository(self.path, key_path=self.key_path, secret_key=secret_key)

        self.assertEqual(reloaded.load(), Credentials(username='alice', password='secret', domain='@cmcc'))
        self.assertFalse(self.key_path.exists())

    def test_load_encrypted_credentials_requires_key(self) -> None:
        secret_key = generate_secret_key().decode('ascii')
        repository = CredentialsRepository(self.path, key_path=self.key_path, secret_key=secret_key)
        repository.save(Credentials(username='alice', password='secret', domain='@cmcc'), save_password=True)

        reloaded = CredentialsRepository(self.path, key_path=self.key_path)
        with self.assertRaises(ValueError):
            reloaded.load()

    def test_load_credentials_from_env(self) -> None:
        loaded = load_credentials_from_env(
            {
                'ECNU_NET_USERNAME': 'alice',
                'ECNU_NET_PASSWORD': 'secret',
                'ECNU_NET_DOMAIN': 'cmcc',
            }
        )

        self.assertEqual(loaded, Credentials(username='alice', password='secret', domain='@cmcc'))

    def test_load_credentials_from_env_requires_both_values(self) -> None:
        with self.assertRaises(ValueError):
            load_credentials_from_env({'ECNU_NET_USERNAME': 'alice'})

    def test_normalize_domain(self) -> None:
        self.assertEqual(normalize_domain(''), DEFAULT_DOMAIN)
        self.assertEqual(normalize_domain('@cmcc'), '@cmcc')
        self.assertEqual(normalize_domain('cmcc'), '@cmcc')
        self.assertEqual(normalize_domain('1 - @cmcc'), '@cmcc')
        self.assertEqual(normalize_domain('@undefined'), DEFAULT_DOMAIN)


if __name__ == '__main__':
    unittest.main()


