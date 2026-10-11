import os
import shlex
import subprocess
import sys
from unittest import mock

from helpers import TempHomeTest

from ugetme import __version__, autostart


class AutostartTest(TempHomeTest):
    def setUp(self):
        super().setUp()
        os.environ["UGETME_STARTUP_DIR"] = str(self.home / "startup")
        self.cmd = ["/opt/bin/ugetme", "serve"]

    def use(self, kind):
        os.environ["UGETME_PLATFORM"] = kind

    def test_linux_writes_a_user_service(self):
        self.use("linux")
        with mock.patch.object(autostart, "serve_command", return_value=self.cmd):
            path = autostart.install()
        self.assertEqual(path.name, "ugetme.service")
        text = path.read_text()
        self.assertIn("ExecStart=" + shlex.join(self.cmd), text)
        self.assertIn("WantedBy=default.target", text)
        self.assertTrue(autostart.installed())
        self.assertTrue(autostart.remove())
        self.assertFalse(path.exists())
        self.assertFalse(autostart.remove())

    def test_linux_without_systemd_writes_a_desktop_autostart_entry(self):
        os.environ.pop("UGETME_PLATFORM", None)
        with mock.patch.object(autostart.sys, "platform", "linux"), \
                mock.patch("platform.release", return_value="6.1.0-generic"), \
                mock.patch.object(autostart.shutil, "which", return_value=None):
            self.assertEqual(autostart.kind(), "xdg")
        self.use("xdg")
        cmd = ["/opt/my tools/ugetme", "serve"]
        with mock.patch.object(autostart, "serve_command", return_value=cmd):
            path = autostart.install()
        self.assertEqual(path.name, "ugetme.desktop")
        text = path.read_text()
        self.assertIn('Exec="/opt/my tools/ugetme" serve', text)
        self.assertIn("Type=Application", text)
        self.assertTrue(autostart.remove())

    def test_macos_writes_a_launch_agent(self):
        self.use("macos")
        with mock.patch.object(autostart, "serve_command", return_value=self.cmd):
            text = autostart.install().read_text()
        self.assertIn("<string>/opt/bin/ugetme</string>", text)
        self.assertIn("<key>RunAtLoad</key>", text)

    def test_macos_logs_to_the_ugetme_home(self):
        self.use("macos")
        os.environ["UGETME_HOME"] = str(self.home / "second")
        with mock.patch.object(autostart, "serve_command", return_value=self.cmd):
            text = autostart.install().read_text()
        self.assertIn(f"<string>{self.home / 'second' / 'serve.log'}</string>", text)

    def test_wsl_writes_a_hidden_startup_script(self):
        self.use("wsl")
        os.environ["WSL_DISTRO_NAME"] = "Test-Distro"
        with mock.patch.object(autostart, "serve_command", return_value=self.cmd):
            path = autostart.install()
        self.assertEqual(path, self.home / "startup" / "ugetme.vbs")
        self.assertEqual(path.read_bytes().decode("utf-8"),
                         'CreateObject("WScript.Shell").Run "wsl.exe -d ""Test-Distro"" -- '
                         '""/opt/bin/ugetme"" ""serve""", 0, False\r\n')

    def test_wsl_without_windows_interop_gives_a_clear_error(self):
        self.use("wsl")
        os.environ.pop("UGETME_STARTUP_DIR")
        with mock.patch.object(autostart.shutil, "which", return_value=None):
            with self.assertRaises(OSError) as raised:
                autostart.target()
        self.assertIn("cmd.exe", str(raised.exception))

    def test_windows_uses_pythonw(self):
        self.use("windows")
        text = autostart.content("windows", self.cmd)
        self.assertIn('pythonw', text)
        self.assertIn('""serve""', text)

    def test_plugin_cache_command_is_not_used(self):
        cached = "/home/u/.claude/plugins/cache/ugetme/ugetme/0.2.0/bin/ugetme"
        with mock.patch.object(autostart.shutil, "which", return_value=cached):
            cmd = autostart.serve_command()
        self.assertEqual(cmd[1], str(self.home / "app" / "bin" / "ugetme"))
        out = subprocess.run([sys.executable, cmd[1], "--version"], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), __version__)

    def test_windows_uses_the_stable_launcher(self):
        text = autostart.content("windows", [sys.executable, str(self.home / "app" / "bin" / "ugetme"), "serve"])
        self.assertIn('""' + str(self.home / "app" / "bin" / "ugetme") + '""', text)
        self.assertNotIn('""-m""', text)

    def test_serve_command_prefers_the_installed_command(self):
        with mock.patch.object(autostart.shutil, "which", return_value="/x/ugetme"):
            self.assertEqual(autostart.serve_command(), ["/x/ugetme", "serve"])
        with mock.patch.object(autostart.shutil, "which", return_value=None):
            cmd = autostart.serve_command()
        self.assertEqual((cmd[0], cmd[-1]), (sys.executable, "serve"))
        self.assertTrue(cmd[1].endswith(os.path.join("bin", "ugetme")))
