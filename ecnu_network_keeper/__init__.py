# Refactored ECNU network login package.

from .config import (
    CONFIG_PATH_ENV_VAR,
    DEFAULT_CONFIG_PATH,
    DEFAULT_KEY_PATH,
    DOMAIN_ENV_VAR,
    KEY_PATH_ENV_VAR,
    PASSWORD_ENV_VAR,
    SECRET_KEY_ENV_VAR,
    USERNAME_ENV_VAR,
    Credentials,
    CredentialsRepository,
    generate_secret_key,
    load_credentials_from_env,
    normalize_domain,
)
from .connectivity import ConnectivityChecker, DEFAULT_TEST_URLS
from .portal import PortalClient, PortalSettings
from .service import AuthResult, AuthStatus, NetworkAuthService
from .tracking import (
    KEEPER_EVENT_LOG_ENV_VAR,
    KEEPER_STATE_PATH_ENV_VAR,
    ConnectivityEventRecorder,
)

__all__ = [
    'AuthResult',
    'AuthStatus',
    'CONFIG_PATH_ENV_VAR',
    'ConnectivityChecker',
    'Credentials',
    'CredentialsRepository',
    'DEFAULT_CONFIG_PATH',
    'DEFAULT_KEY_PATH',
    'DEFAULT_TEST_URLS',
    'DOMAIN_ENV_VAR',
    'KEY_PATH_ENV_VAR',
    'KEEPER_EVENT_LOG_ENV_VAR',
    'KEEPER_STATE_PATH_ENV_VAR',
    'ConnectivityEventRecorder',
    'NetworkAuthService',
    'PASSWORD_ENV_VAR',
    'PortalClient',
    'PortalSettings',
    'SECRET_KEY_ENV_VAR',
    'USERNAME_ENV_VAR',
    'generate_secret_key',
    'load_credentials_from_env',
    'normalize_domain',
]

