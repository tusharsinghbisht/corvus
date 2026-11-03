import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from test_server import ServerDatabaseCase

from corvus.server.database import connect
from corvus.server.operations import backup_status, readiness


class OperationsTests(ServerDatabaseCase):
    def test_readiness_is_authenticated_and_unknown_is_not_reported_as_healthy(self):
        self.assertEqual(self.client.get('/api/operations').status_code, 401)
        self.login()
        response = self.client.get('/api/operations')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['worker']['ready'])
        self.assertFalse(response.json()['backup']['configured'])

    def test_public_status_excludes_secrets_and_flags_stale_restore_or_interrupted_work(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            path.write_text(json.dumps({'configured':True, 'encrypted':True, 'api_key':'NEVER-EXPOSE',
                'last_error':'private-secret-value', 'last_success_at':datetime.now(timezone.utc).isoformat(),
                'in_progress':True, 'last_attempt_at':(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()}))
            safe = backup_status(path)
            self.assertNotIn('NEVER-EXPOSE', json.dumps(safe))
            self.assertNotIn('private-secret-value', json.dumps(safe))
            with connect(self.settings) as db:
                db.execute('UPDATE worker_runtime SET heartbeat_at=now(),analysis_configured=true')
                value = readiness(db, status_path=path)
                self.assertTrue(value['worker']['ready'])
                self.assertTrue(value['worker']['analysis_configured'])
                self.assertTrue(value['backup']['recent'])
                self.assertFalse(value['backup']['restore_recent'])
                self.assertEqual(value['backup']['last_error'], 'backup_interrupted')
                db.execute("UPDATE worker_runtime SET heartbeat_at=now()-interval '6 minutes'")
                self.assertFalse(readiness(db, status_path=path)['worker']['ready'])

    def test_future_or_corrupt_status_is_not_claimed_as_recent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            path.write_text('{broken')
            self.assertFalse(backup_status(path)['configured'])
            path.write_text(json.dumps({'configured':True, 'last_success_at':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()}))
            with connect(self.settings) as db:
                self.assertFalse(readiness(db, status_path=path)['backup']['recent'])
