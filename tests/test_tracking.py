from datetime import datetime
from pathlib import Path
import unittest

from ecnu_network_keeper.tracking import ConnectivityEventRecorder


class ConnectivityEventRecorderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.log_path = Path.cwd() / 'tests' / '_tmp_keeper-events.log'
        self.state_path = Path.cwd() / 'tests' / '_tmp_keeper-state.json'
        for target in (self.log_path, self.state_path):
            if target.exists():
                target.unlink()

    def tearDown(self) -> None:
        for target in (self.log_path, self.state_path):
            if target.exists():
                target.unlink()

    def test_records_startup_and_transition_only_once(self) -> None:
        recorder = ConnectivityEventRecorder(self.log_path, self.state_path)

        recorder.record(False, observed_at=datetime(2026, 3, 17, 10, 0, 0))
        recorder.record(False, observed_at=datetime(2026, 3, 17, 10, 1, 0))
        recorder.record(True, observed_at=datetime(2026, 3, 17, 10, 2, 0))

        lines = self.log_path.read_text(encoding='utf-8').splitlines()

        self.assertEqual(
            lines,
            [
                '[2026-03-17T10:00:00] startup_offline',
                '[2026-03-17T10:02:00] reconnected',
            ],
        )

    def test_from_config_path_prefers_workspace_data_and_logs(self) -> None:
        recorder = ConnectivityEventRecorder.from_config_path(Path.cwd() / 'config.ini', env={})

        self.assertEqual(recorder.log_path, Path.cwd() / 'logs' / 'keeper-events.log')
        self.assertEqual(recorder.state_path, Path.cwd() / 'data' / 'keeper-state.json')


if __name__ == '__main__':
    unittest.main()
