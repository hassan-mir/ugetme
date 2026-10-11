import json
import os
import stat

from helpers import TempHomeTest

from ugetme import config


class ConfigTest(TempHomeTest):
    closed_port = False  # these tests check the real default port, and no test here calls a service

    def test_defaults_when_no_file(self):
        cfg = config.load()
        self.assertEqual((cfg["engine"], cfg["port"], cfg["model"], cfg["context"]), ("claude", 7337, "sonnet", "balanced"))
        self.assertIs(cfg["log"], True)
        self.assertEqual(cfg["openai"], {"base_url": "", "api_key": "", "model": ""})
        self.assertEqual(cfg["check_highlight"], "white")
        self.assertEqual(cfg["live_context_minutes"], 0)

    def test_user_values_override_and_bad_values_fall_back(self):
        (self.home / "config.json").write_text(json.dumps({
            "engine": "bogus", "port": 99999, "timeout_s": 500, "log": "false",
            "openai": {"base_url": "http://x/v1", "nope": 1}, "custom": {"turns": 10}, "scan_roots": ["~/a", 3]}))
        cfg = config.load()
        self.assertEqual((cfg["engine"], cfg["port"], cfg["timeout_s"]), ("claude", 7337, 80))
        self.assertIs(cfg["log"], False)
        self.assertEqual(cfg["openai"]["base_url"], "http://x/v1")
        self.assertNotIn("nope", cfg["openai"])
        self.assertEqual(cfg["custom"]["turns"], 10)
        self.assertEqual(cfg["scan_roots"], ["~/a"])

    def test_corrupt_file_gives_defaults(self):
        (self.home / "config.json").write_text("{not json")
        self.assertEqual(config.load()["engine"], "claude")

    def test_save_round_trip_is_private(self):
        cfg = config.load()
        cfg["engine"] = "openai"
        config.save(cfg)
        self.assertEqual(config.load()["engine"], "openai")
        self.assertEqual(stat.S_IMODE(os.stat(self.home / "config.json").st_mode), 0o600)

    def test_token_is_created_once_and_private(self):
        token = config.token()
        self.assertGreaterEqual(len(token), 20)
        self.assertEqual(config.token(), token)
        self.assertEqual(stat.S_IMODE(os.stat(self.home / "token").st_mode), 0o600)

    def test_context_settings(self):
        cfg = config.load()
        self.assertEqual(config.context_settings(cfg)["turns"], 6)
        cfg["context"] = "custom"
        cfg["custom"]["turns"] = 3
        self.assertEqual(config.context_settings(cfg)["turns"], 3)

    def test_engine_env_and_path(self):
        (self.home / "config.json").write_text(json.dumps({"engine_env": {"ANTHROPIC_BASE_URL": "http://x", "N": 3},
                                                           "env_path": 5}))
        cfg = config.load()
        self.assertEqual((cfg["engine_env"], cfg["env_path"]), ({"ANTHROPIC_BASE_URL": "http://x"}, ""))
        (self.home / "config.json").write_text(json.dumps({"engine_env": "bad"}))
        self.assertEqual(config.load()["engine_env"], {})

    def test_auth_fingerprint(self):
        self.assertEqual(config.auth_fingerprint({"PATH": "/bin"}), "")
        a = config.auth_fingerprint({"CLAUDE_CODE_OAUTH_TOKEN": "t1"})
        self.assertEqual(len(a), 16)
        self.assertNotEqual(a, config.auth_fingerprint({"CLAUDE_CODE_OAUTH_TOKEN": "t2"}))

    def test_token_creates_a_private_home(self):
        home = self.home / "fresh"
        os.environ["UGETME_HOME"] = str(home)
        config.token()
        self.assertEqual(stat.S_IMODE(os.stat(home).st_mode), 0o700)

    def test_token_file_is_created_exclusively(self):
        (self.home / "token").write_text("existing")
        self.assertEqual(config.token(), "existing")

    def test_normalize_config_dir(self):
        self.assertEqual(config.normalize_config_dir(""), config.normalize_config_dir("~/.claude"))
        self.assertNotEqual(config.normalize_config_dir("~/.claude-other"), config.normalize_config_dir(""))

    def test_trusted_logins(self):
        self.assertEqual(config.load()["trusted_logins"], [])
        config.write_json(self.home / "config.json", {"trusted_logins": ["/a", 3, ""]})
        self.assertEqual(config.load()["trusted_logins"], ["/a"])
        config.write_json(self.home / "config.json", {"trusted_logins": "/a"})
        self.assertEqual(config.load()["trusted_logins"], [])

    def test_the_service_url_uses_the_bind_host(self):
        self.assertEqual(config.service_url(7337, "/v1"), f"http://{config.HOST}:7337/v1")
