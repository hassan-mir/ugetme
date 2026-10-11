import os
import unittest
from unittest import mock

from ugetme import clipboard


class ClipboardTest(unittest.TestCase):
    def test_disabled_by_env(self):
        with mock.patch.dict(os.environ, {"UGETME_NO_CLIPBOARD": "1"}):
            self.assertFalse(clipboard.copy("x"))

    def test_macos(self):
        with mock.patch.object(clipboard.sys, "platform", "darwin"):
            self.assertEqual(clipboard.candidates(), [["pbcopy"]])

    def test_wsl_prefers_powershell(self):
        with mock.patch.object(clipboard.sys, "platform", "linux"), \
                mock.patch.object(clipboard, "_is_wsl", return_value=True):
            self.assertEqual(clipboard.candidates()[0][0], "powershell.exe")

    def test_linux_wayland_then_x11(self):
        with mock.patch.object(clipboard.sys, "platform", "linux"), \
                mock.patch.object(clipboard, "_is_wsl", return_value=False), \
                mock.patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}):
            self.assertEqual([c[0] for c in clipboard.candidates()], ["wl-copy", "xclip", "xsel"])

    def test_no_tool_returns_false(self):
        with mock.patch.dict(os.environ), mock.patch.object(clipboard.shutil, "which", return_value=None):
            os.environ.pop("UGETME_NO_CLIPBOARD", None)
            self.assertFalse(clipboard.copy("x"))

    def test_first_working_tool_wins(self):
        ok = mock.Mock(returncode=0)
        with mock.patch.dict(os.environ), mock.patch.object(clipboard, "candidates", return_value=[["a"], ["b"]]), \
                mock.patch.object(clipboard.shutil, "which", side_effect=lambda c: "/bin/" + c), \
                mock.patch.object(clipboard.subprocess, "run", return_value=ok) as run:
            os.environ.pop("UGETME_NO_CLIPBOARD", None)
            self.assertTrue(clipboard.copy("héllo ✦"))
            self.assertEqual(run.call_args[0][0], ["a"])
            self.assertEqual(run.call_args[1]["input"], "héllo ✦".encode("utf-8"))

    def test_read_candidates(self):
        with mock.patch.object(clipboard.sys, "platform", "darwin"):
            self.assertEqual(clipboard.read_candidates(), [["pbpaste"]])
        with mock.patch.object(clipboard.sys, "platform", "win32"):
            self.assertEqual(clipboard.read_candidates()[0][0], "powershell.exe")
            self.assertEqual(clipboard.candidates()[0][0], "powershell.exe")
        with mock.patch.object(clipboard.sys, "platform", "linux"), \
                mock.patch.object(clipboard, "_is_wsl", return_value=False), \
                mock.patch.dict(clipboard.os.environ, {"WAYLAND_DISPLAY": "w"}):
            self.assertEqual([c[0] for c in clipboard.read_candidates()], ["wl-paste", "xclip", "xsel"])
            self.assertIn("text", clipboard.read_candidates()[0])

    def test_paste_uses_the_first_working_tool(self):
        done = mock.Mock(returncode=0, stdout="héllo\r\n".encode("utf-8"))
        with mock.patch.object(clipboard, "read_candidates", return_value=[["missing-tool"], ["cat"]]), \
                mock.patch.object(clipboard.shutil, "which", side_effect=lambda c: c == "cat"), \
                mock.patch.object(clipboard.subprocess, "run", return_value=done):
            self.assertEqual(clipboard.paste(), "héllo")

    def test_paste_without_any_tool_is_none(self):
        with mock.patch.object(clipboard.shutil, "which", return_value=None):
            self.assertIsNone(clipboard.paste())

    def test_tool_names_the_first_reader_on_path(self):
        with mock.patch.object(clipboard, "read_candidates", return_value=[["missing"], ["xclip", "-o"]]), \
                mock.patch.object(clipboard.shutil, "which", side_effect=lambda c: "/usr/bin/xclip" if c == "xclip" else None):
            self.assertEqual(clipboard.tool(), "xclip")
        with mock.patch.object(clipboard.shutil, "which", return_value=None):
            self.assertIsNone(clipboard.tool())
