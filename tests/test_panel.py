import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from trex_sync.panel import Engine, make_panel


class TestPanel(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.lib = self.tmp / "musicas"
        self.lib.mkdir()
        self.cfg = self.tmp / "config.json"
        self.cfg.write_text(json.dumps({"spotify_client_id": "", "playlists": [], "library_dirs": [str(self.lib)],
                                        "output_dir": "saida", "server_port": 0}))
        self.engine = Engine(self.cfg)
        self.srv, self.token = make_panel(self.engine, 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.engine.stop_server()
        self.srv.shutdown()
        self.srv.server_close()

    def req(self, path, method="GET", body=None, token=True, host=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        r = urllib.request.Request(self.base + path, data=data, method=method)
        if token:
            r.add_header("X-Panel-Token", self.token)
        if host:
            r.add_header("Host", host)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_page_requires_token(self):
        self.assertEqual(self.req("/", token=False)[0], 403)
        code, body = self.req(f"/?t={self.token}", token=False)
        self.assertEqual(code, 200)
        self.assertIn(b"spotifiBR", body)

    def test_api_requires_token_and_host(self):
        self.assertEqual(self.req("/api/status", token=False)[0], 401)
        self.assertEqual(self.req("/api/status", host="evil.com")[0], 403)  # DNS rebinding
        self.assertEqual(self.req("/api/sync", "POST", {}, token=False)[0], 403)
        code, body = self.req("/api/status")
        self.assertEqual(code, 200)
        self.assertFalse(json.loads(body)["spotify"]["connected"])

    def test_settings_validation(self):
        ok = {"playlists": ["https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M", "liked"],
              "library_dirs": [str(self.lib)], "mp3_bitrate": "96k"}
        self.assertEqual(self.req("/api/settings", "POST", ok)[0], 200)
        saved = json.loads(self.cfg.read_text())
        self.assertEqual(saved["mp3_bitrate"], "96k")
        self.assertEqual(saved["output_dir"], "saida")  # preserva o resto
        for bad in [{"playlists": ["https://evil.com/x"]}, {"library_dirs": ["/nao/existe"]},
                    {"mp3_bitrate": "9999k"}, {"server_bind": "0.0.0.0"}, {"spotify_client_id": "x y"}]:
            self.assertEqual(self.req("/api/settings", "POST", bad)[0], 400, bad)

    def test_upload(self):
        code, body = self.req("/api/upload?name=Queen%20-%20Bohemian.mp3", "PUT", raw=b"ID3data")
        self.assertEqual(code, 200)
        self.assertTrue((self.lib / "Queen - Bohemian.mp3").exists())
        self.assertEqual(self.req("/api/upload?name=virus.exe", "PUT", raw=b"MZ")[0], 400)
        code, _ = self.req("/api/upload?name=..%2F..%2Fx.mp3", "PUT", raw=b"ID3")
        self.assertEqual(code, 200)
        self.assertFalse((self.tmp / "x.mp3").exists())
        self.assertTrue(any(p.name.endswith(".mp3") and "x" in p.name for p in self.lib.iterdir()))

    def test_server_start_needs_sync_then_works(self):
        self.assertEqual(self.req("/api/server/start", "POST", {})[0], 400)
        out = self.tmp / "saida"
        out.mkdir()
        (out / "manifest.json").write_text('{"version":1,"playlists":[]}')
        cfg = json.loads(self.cfg.read_text())
        cfg["server_bind"] = "127.0.0.1"
        self.cfg.write_text(json.dumps(cfg))
        code, body = self.req("/api/server/start", "POST", {})
        self.assertEqual(code, 200)
        info = json.loads(body)
        self.assertGreaterEqual(len(info["token"]), 40)
        status = json.loads(self.req("/api/status")[1])
        self.assertTrue(status["server"]["running"])
        self.assertEqual(self.req("/api/server/stop", "POST", {})[0], 200)

    def test_sync_without_playlists_reports_error_in_log(self):
        self.assertEqual(self.req("/api/sync", "POST", {})[0], 200)
        for _ in range(50):
            if not self.engine.busy:
                break
            time.sleep(0.05)
        logs = json.loads(self.req("/api/log?since=0")[1])
        self.assertTrue(any("Nenhuma playlist" in r["msg"] for r in logs))

    def test_auto_toggle(self):
        self.assertEqual(self.req("/api/auto", "POST", {"enabled": True, "minutes": 5})[0], 200)
        st = json.loads(self.req("/api/status")[1])
        self.assertEqual(st["auto"], {"enabled": True, "minutes": 5})


if __name__ == "__main__":
    unittest.main()
