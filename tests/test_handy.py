import json
import os
from pathlib import Path
from unittest import mock

from helpers import TempHomeTest

from ugetme import handy

SETTINGS = {"settings": {
    "post_process_enabled": False, "post_process_provider_id": "openai",
    "post_process_providers": [
        {"id": "openai", "base_url": "https://api.example.com/v1", "allow_base_url_edit": False},
        {"id": "custom", "base_url": "http://localhost:11434/v1", "allow_base_url_edit": True, "label": "Custom",
         "models_endpoint": "/models", "supports_structured_output": False}],
    "post_process_models": {"custom": ""}, "post_process_api_keys": {"custom": ""},
    "post_process_prompts": [{"id": "default_improve_transcriptions", "name": "Improve Transcriptions",
                              "prompt": "<transcript>\n${output}\n</transcript>"}],
    "post_process_selected_prompt_id": None,
    "bindings": {"transcribe": {"current_binding": "alt+space"},
                 "transcribe_with_post_process": {"current_binding": "ctrl+shift+space"}},
    "auto_submit": False, "auto_submit_key": "enter", "other_setting": 1}}


class HandyTest(TempHomeTest):
    def setUp(self):
        super().setUp()
        self.handy_file.parent.mkdir()
        self.original = json.dumps(SETTINGS, indent=2)
        self.handy_file.write_text(self.original)

    def custom(self):
        return next(p for p in self.handy_settings()["post_process_providers"] if p["id"] == "custom")

    def test_linux_paths_follow_xdg_data_home(self):
        os.environ.pop("UGETME_HANDY_SETTINGS", None)
        with mock.patch.object(handy.sys, "platform", "linux"), mock.patch.object(handy, "_is_wsl", return_value=False), \
                mock.patch.dict(os.environ, {"XDG_DATA_HOME": "/data/me"}):
            self.assertIn(Path("/data/me/com.pais.handy/settings_store.json"), handy.candidate_paths())

    def test_find_settings_uses_the_override(self):
        self.assertEqual(handy.find_settings(), self.handy_file)

    def test_configure_sets_provider_and_prompt_and_keeps_the_rest(self):
        backup = handy.configure(self.handy_file, 7337, "tok")
        s = self.handy_settings()
        self.assertEqual(self.custom()["base_url"], "http://127.0.0.1:7337/v1")
        self.assertEqual((s["post_process_provider_id"], s["post_process_models"]["custom"],
                          s["post_process_api_keys"]["custom"]), ("custom", "ugetme", "tok"))
        self.assertIs(s["post_process_enabled"], True)
        self.assertEqual(s["post_process_selected_prompt_id"], "ugetme")
        self.assertIn({"id": "ugetme", "name": "ugetme", "prompt": "${output}"}, s["post_process_prompts"])
        self.assertEqual(s["other_setting"], 1)
        self.assertEqual(s["bindings"]["transcribe"]["current_binding"], "alt+space")
        self.assertEqual(backup.read_text(), self.original)

    def test_configure_twice_keeps_one_ugetme_prompt(self):
        handy.configure(self.handy_file, 7337, "tok")
        handy.configure(self.handy_file, 7337, "tok")
        self.assertEqual(sum(p["id"] == "ugetme" for p in self.handy_settings()["post_process_prompts"]), 1)

    def test_swap_hotkeys_and_auto_submit(self):
        handy.configure(self.handy_file, 7337, "tok", swap_hotkeys=True, auto_submit=True)
        b = self.handy_settings()["bindings"]
        self.assertEqual((b["transcribe"]["current_binding"], b["transcribe_with_post_process"]["current_binding"]),
                         ("ctrl+shift+space", "alt+space"))
        self.assertEqual((self.handy_settings()["auto_submit"], self.handy_settings()["auto_submit_key"]), (True, "enter"))

    def test_swap_back_when_the_main_hotkey_is_not_wanted(self):
        handy.configure(self.handy_file, 7337, "tok", swap_hotkeys=True)
        handy.configure(self.handy_file, 7337, "tok", swap_hotkeys=False)
        b = self.handy_settings()["bindings"]
        self.assertEqual((b["transcribe"]["current_binding"], b["transcribe_with_post_process"]["current_binding"]),
                         ("alt+space", "ctrl+shift+space"))
        handy.configure(self.handy_file, 7337, "tok", swap_hotkeys=False)  # not swapped: nothing to swap back
        self.assertEqual(self.handy_settings()["bindings"]["transcribe"]["current_binding"], "alt+space")
        handy.configure(self.handy_file, 7337, "tok", swap_hotkeys=True)
        self.assertEqual(self.handy_settings()["bindings"]["transcribe"]["current_binding"], "ctrl+shift+space")
        handy.configure(self.handy_file, 7337, "tok")  # None leaves the hotkeys as they are
        self.assertEqual(self.handy_settings()["bindings"]["transcribe"]["current_binding"], "ctrl+shift+space")
        self.assertTrue(handy.is_set_up(self.handy_file))

    def test_missing_custom_provider_is_added(self):
        data = json.loads(self.original)
        data["settings"]["post_process_providers"] = data["settings"]["post_process_providers"][:1]
        self.handy_file.write_text(json.dumps(data))
        handy.configure(self.handy_file, 7337, "tok")
        self.assertEqual(self.custom()["base_url"], "http://127.0.0.1:7337/v1")

    def test_second_setup_keeps_the_original_backup_and_hotkeys(self):
        handy.configure(self.handy_file, 7337, "tok", swap_hotkeys=True)
        handy.configure(self.handy_file, 7337, "tok", swap_hotkeys=True)
        self.assertEqual(self.handy_settings()["bindings"]["transcribe"]["current_binding"], "ctrl+shift+space")
        self.assertEqual(len(handy.backups(self.handy_file)), 1)
        self.assertEqual(handy.undo(self.handy_file), handy.backups(self.handy_file)[0])
        self.assertEqual(self.handy_file.read_text(), self.original)
        handy.configure(self.handy_file, 7337, "tok", swap_hotkeys=True)
        self.assertEqual(self.handy_settings()["bindings"]["transcribe"]["current_binding"], "ctrl+shift+space")

    def test_structured_output_is_turned_off(self):
        data = json.loads(self.original)
        data["settings"]["post_process_providers"][1]["supports_structured_output"] = True
        self.handy_file.write_text(json.dumps(data))
        handy.configure(self.handy_file, 7337, "tok")
        self.assertIs(self.custom()["supports_structured_output"], False)

    def test_describe_warns_when_both_hotkeys_are_the_same(self):
        handy.configure(self.handy_file, 7337, "tok")
        data = json.loads(self.handy_file.read_text())
        data["settings"]["bindings"]["transcribe"]["current_binding"] = "ctrl+shift+space"
        self.handy_file.write_text(json.dumps(data))
        self.assertIn("both Handy hotkeys are ctrl+shift+space", handy.describe())
        self.assertIn("plain transcription", handy.describe())

    def test_describe_warns_when_the_port_changed(self):
        handy.configure(self.handy_file, 7337, "tok")
        self.assertIn("points to port 7337", handy.describe(port=7447))
        self.assertIn("ugetme handy setup", handy.describe(port=7447))

    def test_an_older_localhost_setup_gives_no_warning(self):
        handy.configure(self.handy_file, 7337, "tok")
        data = json.loads(self.handy_file.read_text())
        next(p for p in data["settings"]["post_process_providers"] if p["id"] == "custom")["base_url"] = "http://localhost:7337/v1"
        self.handy_file.write_text(json.dumps(data))
        self.assertTrue(handy.describe(port=7337).startswith("set up (http://localhost:7337/v1)"))

    def test_status_survives_odd_settings_shapes(self):
        set_up = {"post_process_enabled": True, "post_process_provider_id": "custom",
                  "post_process_selected_prompt_id": "ugetme"}
        unknown = "set up (?) · ugetme hotkey: ?"
        for data, port, described in (
                ([], 7337, "found, unreadable"),
                (dict(set_up, bindings=["a"]), None, unknown),
                (dict(set_up, bindings={"transcribe": "a", "transcribe_with_post_process": 1}), None, unknown),
                (dict(set_up, post_process_providers=3), None, unknown),
                (dict(set_up, post_process_providers=[{"id": "custom", "base_url": None}]), 7337,
                 "set up, but Handy points to port ? and ugetme uses 7337. Quit Handy and run: ugetme handy setup")):
            self.handy_file.write_text(json.dumps(data))
            self.assertEqual(handy.describe(port=port), described)
            self.assertEqual(handy.is_set_up(self.handy_file), data != [])

    def test_is_running_override_and_describe(self):
        self.assertFalse(handy.is_running())
        os.environ["UGETME_HANDY_RUNNING"] = "1"
        self.assertTrue(handy.is_running())
        self.assertEqual(handy.describe(), "found, not set up for ugetme")
        handy.configure(self.handy_file, 7337, "tok")
        self.assertEqual(handy.describe(), "set up (http://127.0.0.1:7337/v1) · ugetme hotkey: ctrl+shift+space")
