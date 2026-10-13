"""Offline tests: config merge, selectors override, chrome discovery, captions/finish with real ffmpeg.

Run: python -m unittest discover -s tests -v   (needs ffmpeg + pillow; no browser, no network)
"""
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def load_flow(home):
    os.environ["FLOW_DIRECTOR_HOME"] = str(home)
    import flow
    return importlib.reload(flow)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.flow = load_flow(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_then_partial_override_merges_nested(self):
        Path(self.tmp.name, "config.json").write_text(json.dumps({"format": {"width": 720}, "mode": "auto"}))
        cfg = self.flow.load_config()
        self.assertEqual(cfg["format"], {"width": 720, "height": 1920, "duration": 10})
        self.assertEqual(cfg["mode"], "auto")
        self.assertTrue(cfg["captions"]["enabled"])

    def test_setup_saves_and_reports_next_steps(self):
        parser = self.flow.build_parser()
        args = parser.parse_args(["setup", "--no-browser", "--characters", "Mia, Leo", "--width", "720",
                                  "--height", "1280", "--captions", "off", "--mode", "auto", "--port", "9777"])
        result = self.flow.cmd_setup(args, self.flow.load_config())
        saved = json.loads(Path(self.tmp.name, "config.json").read_text())
        self.assertEqual(saved["characters"], ["Mia", "Leo"])
        self.assertEqual((saved["format"]["width"], saved["format"]["height"]), (720, 1280))
        self.assertFalse(saved["captions"]["enabled"])
        self.assertEqual(saved["port"], 9777)
        self.assertEqual(result["login"], "no_browser")
        self.assertTrue(any("sign in" in s.lower() for s in result["next"]))
        self.assertTrue(any("project" in s.lower() for s in result["next"]))

    def test_selector_override_wins(self):
        Path(self.tmp.name, "selectors.json").write_text(json.dumps({"composer": "#mine", "stop_patterns": {"policy": "xyz"}}))
        sel = self.flow.selectors()
        self.assertEqual(sel["composer"], "#mine")
        self.assertEqual(sel["stop_patterns"]["policy"], "xyz")
        self.assertIn("challenge", sel["stop_patterns"])  # untouched keys survive
        self.assertEqual(sel["send_button"], json.loads((ROOT / "selectors.json").read_text())["send_button"])

    def test_project_id_extraction(self):
        pid = "12345678-1234-1234-1234-123456789abc"
        self.assertEqual(self.flow._project_id(f"https://flow.google.com/u/0/project/{pid}"), pid)
        self.assertIsNone(self.flow._project_id("https://flow.google.com/"))

    def test_credits_tracking(self):
        parser = self.flow.build_parser()
        cfg = self.flow.load_config()
        self.flow.cmd_credits(parser.parse_args(["credits", "--add", "4"]), cfg)
        out = self.flow.cmd_credits(parser.parse_args(["credits", "--add", "3"]), cfg)
        self.assertEqual((out["used"], out["remaining"]), (7, cfg["max_credits"] - 7))
        self.assertEqual(self.flow.cmd_credits(parser.parse_args(["credits", "--reset"]), cfg)["used"], 0)


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.flow = load_flow(self.tmp.name)
        self.sel = self.flow.selectors()

    def tearDown(self):
        self.tmp.cleanup()

    def snap(self, **kw):
        base = dict(url="https://flow.google.com/u/0/project/x", dialog="", alerts="", permission="",
                    agent_panel=True, composer=True)
        return {**base, **kw}

    def test_states(self):
        c = self.flow.classify
        self.assertEqual(c(self.snap(), self.sel), "ready")
        self.assertEqual(c(self.snap(url="https://accounts.google.com/signin"), self.sel), "signed_out")
        self.assertEqual(c(self.snap(alerts="Unusual traffic detected"), self.sel), "challenge")
        self.assertEqual(c(self.snap(dialog="You are out of credits"), self.sel), "credits")
        self.assertEqual(c(self.snap(permission="Generate 8s video for 20 credits"), self.sel), "permission_card")
        self.assertEqual(c(self.snap(agent_panel=False), self.sel), "unknown")


class BrowserDiscoveryTests(unittest.TestCase):
    def test_explicit_chrome_path_is_used_when_it_exists(self):
        tmp = tempfile.TemporaryDirectory()
        flow = load_flow(tmp.name)
        fake = Path(tmp.name, "chrome-fake")
        fake.write_text("x")
        self.assertEqual(flow.find_chrome(str(fake)), str(fake))
        tmp.cleanup()

    def test_which_fallback(self):
        tmp = tempfile.TemporaryDirectory()
        flow = load_flow(tmp.name)
        with mock.patch.object(flow.shutil, "which", side_effect=lambda n: "/x/chromium" if n == "chromium" else None), \
                mock.patch.object(flow.os, "name", "posix"), mock.patch.object(flow.sys, "platform", "linux"):
            self.assertEqual(flow.find_chrome(None), "/x/chromium")
        tmp.cleanup()

    def test_missing_browser_gives_actionable_error(self):
        tmp = tempfile.TemporaryDirectory()
        flow = load_flow(tmp.name)
        cfg = flow.load_config()
        with mock.patch.object(flow, "cdp_alive", return_value=False), mock.patch.object(flow, "find_chrome", return_value=None):
            with self.assertRaises(flow.FlowError) as ctx:
                flow.browser_start(cfg)
        self.assertIn("bootstrap", ctx.exception.hint)
        tmp.cleanup()


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class CaptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.clip = Path(cls.tmp.name, "clip.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=640x360:rate=24",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest", str(cls.clip)], check=True)
        import captions
        cls.captions = captions

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_scale_pad_without_caption(self):
        out = self.captions.finish(self.clip, Path(self.tmp.name, "plain.mp4"), 720, 1280)
        self.assertEqual((out["width"], out["height"]), (720, 1280))
        self.assertTrue(out["has_audio"])
        self.assertAlmostEqual(out["duration"], 2.0, delta=0.2)

    def test_caption_with_hostile_text_does_not_break_ffmpeg(self):
        text = "It's 5:00 'quoted' \"double\" %{expr} \\ , ; [x] émoji 🎬"
        out = self.captions.finish(self.clip, Path(self.tmp.name, "cap.mp4"), 720, 1280, caption=text,
                                   layout={"y": 0.2, "start": 0.2})
        self.assertEqual((out["width"], out["height"]), (720, 1280))
        self.assertIsNotNone(out["caption"])

    def test_long_caption_shrinks_to_fit_and_stays_in_frame(self):
        info = self.captions.render_overlay("word " * 40, 720, 1280, {"max_lines": 3}, self.captions.find_font(),
                                            Path(self.tmp.name, "o.png"))
        self.assertLessEqual(info["lines"], 3)
        left, top, right, bottom = info["bounds"]
        self.assertTrue(0 <= left and right <= 720 and 0 <= top and bottom <= 1280)

    def test_trim(self):
        out = self.captions.finish(self.clip, Path(self.tmp.name, "trim.mp4"), 360, 640, trim=1)
        self.assertAlmostEqual(out["duration"], 1.0, delta=0.2)

    def test_missing_input_is_clear(self):
        with self.assertRaises(FileNotFoundError):
            self.captions.finish(Path(self.tmp.name, "nope.mp4"), Path(self.tmp.name, "o.mp4"), 100, 100)


class CliContractTests(unittest.TestCase):
    def test_errors_are_json_with_hint_and_exit_2(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, FLOW_DIRECTOR_HOME=home, FLOW_NO_REEXEC="1")
            done = subprocess.run([sys.executable, str(ROOT / "scripts" / "flow.py"), "snapshot"],
                                  capture_output=True, text=True, env=env)
        payload = json.loads(done.stdout)
        self.assertEqual(done.returncode, 2)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["hint"])

    def test_help_lists_all_commands(self):
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / "flow.py"), "--help"], capture_output=True, text=True,
                              env=dict(os.environ, FLOW_NO_REEXEC="1"))
        for command in ("setup", "doctor", "browser", "send", "attach", "wait", "download", "captions", "inspect", "eval"):
            self.assertIn(command, done.stdout)


if __name__ == "__main__":
    unittest.main()
