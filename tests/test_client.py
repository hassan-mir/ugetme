import os
import signal
import stat
from unittest import mock

from helpers import ServerTest, TempHomeTest, free_port

from ugetme import client


class ClientTest(ServerTest):
    def test_request_and_health(self):
        self.assertTrue(client.health()["ok"])
        self.assertEqual(client.request("GET", "/v1/models")["data"][0]["id"], "ugetme")

    def test_bad_token_raises(self):
        with mock.patch.object(type(self.service), "token", new_callable=mock.PropertyMock, return_value="other"):
            with self.assertRaises(client.ClientError) as ctx:
                client.request("GET", "/v1/models")
        self.assertIn("401", str(ctx.exception))


def _kill(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


class ClientStartTest(TempHomeTest):
    def test_health_is_none_when_nothing_listens(self):
        self.assertIsNone(client.health(timeout=0.2))
        with self.assertRaises(client.ClientError):
            client.request("GET", "/v1/models", timeout=0.5)

    def test_start_a_private_detached_service_and_stop_it(self):
        home = self.home / "fresh"
        os.environ["UGETME_HOME"] = str(home)
        self.set_config(port=free_port())
        self.assertEqual(stat.S_IMODE(os.stat(home).st_mode), 0o700)
        log = home / "serve.log"
        self.assertTrue(client.ensure_running(wait_s=10), log.read_text() if log.exists() else "no serve.log")
        pid = client.health()["pid"]
        self.addCleanup(_kill, pid)
        self.assertNotEqual(pid, os.getpid())
        self.assertEqual(stat.S_IMODE(os.stat(home / "serve.log").st_mode), 0o600)
        with mock.patch.object(client, "start_detached") as start:
            self.assertTrue(client.ensure_running(wait_s=1))
        start.assert_not_called()
        self.assertTrue(client.stop(wait_s=5))
        self.assertIsNone(client.health())
        self.assertIsNone(client.stop(wait_s=1))
