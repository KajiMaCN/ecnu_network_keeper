from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping


KEEPER_EVENT_LOG_ENV_VAR = 'ECNU_KEEPER_EVENT_LOG'
KEEPER_STATE_PATH_ENV_VAR = 'ECNU_KEEPER_STATE_PATH'


@dataclass(frozen=True)
class ConnectivityState:
    online: bool
    observed_at: str


class ConnectivityEventRecorder:
    def __init__(self, log_path: Path, state_path: Path) -> None:
        self.log_path = log_path
        self.state_path = state_path

    @classmethod
    def from_config_path(
        cls,
        config_path: Path,
        env: Mapping[str, str] | None = None,
    ) -> 'ConnectivityEventRecorder':
        source = os.environ if env is None else env
        default_log_path, default_state_path = _default_runtime_paths(config_path)
        log_path = Path(source.get(KEEPER_EVENT_LOG_ENV_VAR, '').strip() or default_log_path)
        state_path = Path(source.get(KEEPER_STATE_PATH_ENV_VAR, '').strip() or default_state_path)
        return cls(log_path=log_path, state_path=state_path)

    def record(self, online: bool, *, observed_at: datetime | None = None) -> bool:
        timestamp = (observed_at or datetime.now()).replace(microsecond=0).isoformat()
        current = ConnectivityState(online=online, observed_at=timestamp)
        previous = self._load_state()

        if previous is None:
            self._append_event(current, 'startup_online' if online else 'startup_offline')
            self._save_state(current)
            return True

        if previous.online == current.online:
            return False

        self._append_event(current, 'reconnected' if online else 'disconnected')
        self._save_state(current)
        return True

    def _load_state(self) -> ConnectivityState | None:
        if not self.state_path.exists():
            return None

        data = json.loads(self.state_path.read_text(encoding='utf-8'))
        return ConnectivityState(
            online=bool(data['online']),
            observed_at=str(data['observed_at']),
        )

    def _save_state(self, state: ConnectivityState) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'online': state.online,
            'observed_at': state.observed_at,
        }
        self.state_path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2) + '\n',
            encoding='utf-8',
        )

    def _append_event(self, state: ConnectivityState, event: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        line = f'[{state.observed_at}] {event}\n'
        with self.log_path.open('a', encoding='utf-8') as handle:
            handle.write(line)


def _default_runtime_paths(config_path: Path) -> tuple[Path, Path]:
    workspace_root = Path.cwd()
    workspace_data = workspace_root / 'data'
    workspace_logs = workspace_root / 'logs'
    if workspace_data.exists() or workspace_logs.exists():
        return workspace_logs / 'keeper-events.log', workspace_data / 'keeper-state.json'

    config_dir = config_path.expanduser().resolve().parent
    return config_dir / 'keeper-events.log', config_dir / 'keeper-state.json'
