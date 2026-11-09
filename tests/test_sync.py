import json
import tempfile
import unittest
from pathlib import Path

from spotifibr.library import Library, LocalFile, normalize
from spotifibr.spotify import Track, parse_playlist_id, track_from_json
from spotifibr.sync import TRANSFER_DIR, State, confirm_transfer, sync_playlist, write_missing


def T(i, artist, title):
    return Track(i, title, (artist,), "", 1000, f"https://open.spotify.com/track/{i}")


class TestNormalize(unittest.TestCase):
    def test_noise_and_accents(self):
        self.assertEqual(normalize("Coração (feat. Fulano) - Remastered 2011"), "coracao")
        self.assertEqual(normalize("Song [Live]"), "song")
        self.assertEqual(normalize("Simon & Garfunkel"), "simon and garfunkel")

    def test_parse_playlist(self):
        self.assertEqual(parse_playlist_id("https://open.spotify.com/playlist/abc123?si=x"), "abc123")
        self.assertEqual(parse_playlist_id("spotify:playlist:abc123"), "abc123")
        self.assertEqual(parse_playlist_id("Curtidas"), "liked")

    def test_track_from_json_skips_local_and_episodes(self):
        self.assertIsNone(track_from_json({"type": "episode", "id": "x"}))
        self.assertIsNone(track_from_json({"is_local": True, "id": None}))
        t = track_from_json({"id": "1", "name": "A", "artists": [{"name": "B"}], "type": "track"})
        self.assertEqual(t.display, "B - A")


class TestSync(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.lib_dir = self.tmp / "lib"
        self.lib_dir.mkdir()
        for name in ["Legião Urbana - Tempo Perdido.mp3", "03 - Queen - Bohemian Rhapsody.mp3",
                     "Daft Punk - One More Time.mp3"]:
            (self.lib_dir / name).write_bytes(b"ID3fake")
        self.out = self.tmp / "out"
        self.state = State(self.out / ".state.json")

    def lib(self):
        return Library.scan([self.lib_dir])

    def test_match_fuzzy(self):
        lib = self.lib()
        self.assertIsNotNone(lib.find(T("1", "Legiao Urbana", "Tempo Perdido - Remastered")))
        self.assertIsNotNone(lib.find(T("2", "Queen", "Bohemian Rhapsody")))
        self.assertIsNone(lib.find(T("3", "Queen", "Another One Bites the Dust")))

    def test_full_cycle_only_new_tracks(self):
        tracks = [T("1", "Legião Urbana", "Tempo Perdido"), T("2", "Queen", "Bohemian Rhapsody"),
                  T("9", "Ninguém", "Não Tenho")]
        r = sync_playlist("p1", "Treino", tracks, self.lib(), self.state, self.out)
        self.assertEqual(len(r.new), 2)
        self.assertEqual([t.id for t in r.missing], ["9"])
        self.assertEqual(len(list((self.out / TRANSFER_DIR / "Treino").iterdir())), 2)
        self.assertTrue(write_missing([r], self.out).exists())

        self.assertEqual(confirm_transfer(self.state, self.out), 2)
        self.assertFalse((self.out / TRANSFER_DIR).exists())

        # adiciona uma faixa nova e remove uma antiga no Spotify
        tracks2 = [T("2", "Queen", "Bohemian Rhapsody"), T("4", "Daft Punk", "One More Time")]
        r2 = sync_playlist("p1", "Treino", tracks2, self.lib(), State(self.out / ".state.json"), self.out)
        self.assertEqual(r2.new, ["Daft Punk - One More Time.mp3"])
        self.assertEqual(r2.removed, ["Legião Urbana - Tempo Perdido.mp3"])
        self.assertFalse((self.out / "Treino" / "Legião Urbana - Tempo Perdido.mp3").exists())

    def test_resync_without_confirm_is_idempotent(self):
        tracks = [T("2", "Queen", "Bohemian Rhapsody")]
        sync_playlist("p1", "X", tracks, self.lib(), self.state, self.out)
        r = sync_playlist("p1", "X", tracks, self.lib(), self.state, self.out)
        self.assertEqual(len(r.new), 1)
        data = json.loads((self.out / ".state.json").read_text())
        self.assertEqual(len(data["playlists"]["p1"]["pending"]), 1)

    def test_downloader_hook(self):
        dl = self.tmp / "dl"
        script = self.tmp / "fake_dl.py"
        script.write_text("import sys,pathlib;pathlib.Path(sys.argv[1],sys.argv[2]+' - '+sys.argv[3]+'.mp3').write_bytes(b'x')")
        import sys
        cmd = [sys.executable, str(script), "{dir}", "{artist}", "{title}"]
        from spotifibr.sync import run_downloader
        import unittest.mock as um
        with um.patch("subprocess.run") as run:
            run_downloader(["x", "{dir}/{artist}.{output-ext}"], T("7", "A", "B"), dl)
            self.assertEqual(run.call_args[0][0], ["x", f"{dl}/A.{{output-ext}}"])
        r = sync_playlist("p2", "Y", [T("7", "Novo", "Single")], self.lib(), self.state, self.out,
                          downloader=cmd, download_dir=dl)
        self.assertEqual(r.new, ["Novo - Single.mp3"])


if __name__ == "__main__":
    unittest.main()


class TestManifestAndServer(unittest.TestCase):
    TOKEN = "t" * 40

    def setUp(self):
        import threading

        from spotifibr.server import make_server
        from spotifibr.sync import write_manifest

        tmp = Path(tempfile.mkdtemp())
        lib = tmp / "lib"
        lib.mkdir()
        (lib / "Queen - Bohemian Rhapsody.mp3").write_bytes(b"ID3abc")
        self.out = tmp / "out"
        r = sync_playlist("p1", "Rock", [T("2", "Queen", "Bohemian Rhapsody"), T("3", "X", "Y")],
                          Library.scan([lib]), State(self.out / ".trex_state.json"), self.out)
        write_missing([r], self.out)
        write_manifest([r], self.out)
        (tmp / "segredo.txt").write_text("senha do PC")
        (self.out / "Rock" / "link.mp3").symlink_to(tmp / "segredo.txt")
        self.srv = make_server(self.out, 0, self.TOKEN, "127.0.0.1")
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def get(self, path, token=None):
        import urllib.error
        import urllib.request

        req = urllib.request.Request(self.base + path)
        if token:
            req.add_header("X-Trex-Token", token)
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, b""

    def test_manifest_content(self):
        m = json.loads((self.out / "manifest.json").read_text())
        self.assertEqual(m["playlists"][0]["tracks"],
                         [{"id": "2", "t": "Bohemian Rhapsody", "a": "Queen",
                           "p": "Rock/Queen - Bohemian Rhapsody.mp3", "s": 6}])

    def test_auth_header_only(self):
        self.assertEqual(self.get("/manifest.json")[0], 401)
        self.assertEqual(self.get(f"/manifest.json?k={self.TOKEN}")[0], 401)  # token na URL não vale
        self.assertEqual(self.get("/manifest.json", "errado")[0], 401)
        code, body = self.get("/manifest.json", self.TOKEN)
        self.assertEqual((code, json.loads(body)["version"]), (200, 1))
        code, body = self.get("/Rock/Queen%20-%20Bohemian%20Rhapsody.mp3", self.TOKEN)
        self.assertEqual((code, body), (200, b"ID3abc"))

    def test_only_manifest_files_are_served(self):
        for path in ["/", "/Rock/", "/_FALTANDO.txt", "/.trex_state.json", "/_PARA_TRANSFERIR/Rock/Queen%20-%20Bohemian%20Rhapsody.mp3",
                     "/../segredo.txt", "/Rock/../../segredo.txt", "/%2e%2e/segredo.txt", "/Rock/link.mp3"]:
            self.assertEqual(self.get(path, self.TOKEN)[0], 404, path)

    def test_symlink_in_manifest_is_blocked(self):
        from spotifibr.server import Allowlist

        m = json.loads((self.out / "manifest.json").read_text())
        m["playlists"][0]["tracks"].append({"id": "9", "t": "x", "a": "y", "p": "Rock/link.mp3", "s": 1})
        (self.out / "manifest.json").write_text(json.dumps(m))
        self.assertIsNone(Allowlist(self.out).resolve("Rock/link.mp3"))

    def test_bruteforce_lockout(self):
        from spotifibr import server

        for _ in range(server.MAX_FAILS):
            self.get("/manifest.json", "chute")
        self.assertEqual(self.get("/manifest.json", self.TOKEN)[0], 429)

    def test_methods_and_weak_token(self):
        import urllib.error
        import urllib.request

        from spotifibr.server import make_server

        req = urllib.request.Request(self.base + "/manifest.json", data=b"x", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 405)
        with self.assertRaises(RuntimeError):
            make_server(self.out, 0, "curto")


class TestSecurityHelpers(unittest.TestCase):
    def test_local_clients(self):
        from spotifibr.server import is_local_client

        for ip in ["127.0.0.1", "192.168.0.5", "10.1.2.3", "172.16.0.9", "100.101.102.103", "::1", "fe80::1"]:
            self.assertTrue(is_local_client(ip), ip)
        for ip in ["8.8.8.8", "200.160.2.3", "2001:4860::8888", "lixo"]:
            self.assertFalse(is_local_client(ip), ip)

    def test_token_generation_and_permissions(self):
        import os
        import stat

        from spotifibr.server import load_or_create_token

        tmp = Path(tempfile.mkdtemp())
        tok = load_or_create_token("TROQUE-POR-UMA-SENHA-LONGA", tmp / ".tok")
        self.assertGreaterEqual(len(tok), 40)
        self.assertEqual(stat.S_IMODE(os.stat(tmp / ".tok").st_mode), 0o600)
        self.assertEqual(load_or_create_token("", tmp / ".tok"), tok)  # estável
        with self.assertRaises(RuntimeError):
            load_or_create_token("senha123", tmp / ".tok")

    def test_spotify_token_file_private(self):
        import os
        import stat

        from spotifibr.spotify import SpotifyClient

        tmp = Path(tempfile.mkdtemp())
        sp = SpotifyClient("cid", tmp / "tok.json")
        sp._save({"access_token": "a", "refresh_token": "r", "expires_at": 0})
        self.assertEqual(stat.S_IMODE(os.stat(tmp / "tok.json").st_mode), 0o600)
        with self.assertRaises(ValueError):
            SpotifyClient("cid", tmp / "x.json", redirect_uri="http://192.168.0.2:8888/callback")

    def test_ids_and_names(self):
        from spotifibr.spotify import parse_playlist_id, track_from_json
        from spotifibr.sync import safe_name

        self.assertIsNone(track_from_json({"id": "../../etc", "name": "x", "type": "track"}))
        with self.assertRaises(ValueError):
            parse_playlist_id("https://evil.com/playlist/abc")
        with self.assertRaises(ValueError):
            parse_playlist_id("abc/../me")
        for bad in ["..", ".", "...", "../x", ".ssh", "CON", ""]:
            name = safe_name(bad)
            self.assertNotIn("/", name)
            self.assertFalse(name.startswith("."), bad)
            self.assertNotIn(name.lower(), ("con",))

    def test_playlist_named_dotdot_stays_inside(self):
        tmp = Path(tempfile.mkdtemp())
        lib = tmp / "lib"
        lib.mkdir()
        (lib / "A - B.mp3").write_bytes(b"x")
        out = tmp / "out"
        sync_playlist("p", "..", [T("1", "A", "B")], Library.scan([lib]), State(out / "s.json"), out)
        self.assertFalse((tmp / "A - B.mp3").exists())
        self.assertTrue(any(out.rglob("A - B.mp3")))

    def test_downloader_argument_injection(self):
        import unittest.mock as um

        from spotifibr.sync import run_downloader

        evil = Track("abc", "--exec=rm -rf ~", ("-oProxyCommand=x",), "", 0, "https://open.spotify.com/track/abc")
        with um.patch("subprocess.run") as run:
            run_downloader(["dl", "{artist}", "{title}", "{url}"], evil, Path(tempfile.mkdtemp()))
            args = run.call_args[0][0]
            self.assertTrue(all(not a.startswith("-") for a in args[1:]), args)
            self.assertFalse(run.call_args.kwargs.get("shell"))
        bad_url = Track("abc", "t", ("a",), "", 0, "file:///etc/passwd")
        with um.patch("subprocess.run") as run:
            run_downloader(["dl", "{url}"], bad_url, Path(tempfile.mkdtemp()))
            run.assert_not_called()


class TestLinks(unittest.TestCase):
    def test_track_extra_fields(self):
        t = track_from_json({"id": "abc123", "name": "Faixa de Exemplo", "type": "track", "duration_ms": 222000,
                             "artists": [{"name": "Banda Fictícia"}],
                             "album": {"name": "Álbum Demo", "release_date": "2019-05-01"},
                             "external_ids": {"isrc": "brxyz1900001"}})
        self.assertEqual((t.isrc, t.year), ("BRXYZ1900001", "2019"))
        bad = track_from_json({"id": "abc", "name": "x", "type": "track", "external_ids": {"isrc": "<script>"}})
        self.assertEqual(bad.isrc, "")

    def test_write_links_txt_and_csv(self):
        import csv

        from spotifibr.links import write_links

        t = Track("abc123", "Faixa de Exemplo", ("Banda Fictícia",), "Álbum Demo", 222000,
                  "https://open.spotify.com/track/abc123", "BRXYZ1900001", "2019")
        out = Path(tempfile.mkdtemp()) / "LINKS.txt"
        txt, csv_path = write_links([("Rock Exemplo", [t]), ("Vazia", [])], out, "teste")
        body = txt.read_text(encoding="utf-8")
        for expected in ["== Rock Exemplo (1) ==", "Banda Fictícia – Faixa de Exemplo", "Álbum Demo (2019) · 3:42 · ISRC: BRXYZ1900001",
                         "https://open.spotify.com/track/abc123", "https://song.link/s/abc123",
                         "https://music.apple.com/br/search?term=Banda%20Fict%C3%ADcia%20Faixa%20de%20Exemplo"]:
            self.assertIn(expected, body)
        self.assertNotIn("Vazia", body)
        rows = list(csv.reader(open(csv_path, encoding="utf-8-sig"), delimiter=";"))
        self.assertEqual(rows[1][:7], ["Rock Exemplo", "Banda Fictícia", "Faixa de Exemplo", "Álbum Demo", "2019", "3:42", "BRXYZ1900001"])
        self.assertIsNone(write_links([("x", [])], out, "teste"))
        self.assertFalse(out.exists())

    def test_run_links_with_fake_spotify(self):
        import unittest.mock as um

        from spotifibr.config import Config
        from spotifibr.runner import run_links

        tmp = Path(tempfile.mkdtemp())
        (tmp / "config.json").write_text(json.dumps({"spotify_client_id": "cid", "playlists": ["liked"], "output_dir": "saida"}))
        cfg = Config.load(tmp / "config.json")
        fake = um.MagicMock()
        fake.playlist_name.return_value = "Favoritas (exemplo)"
        fake.playlist_tracks.return_value = [T("a1", "Banda Fictícia", "Faixa 1"), T("a1", "Banda Fictícia", "Faixa 1"),
                                             T("a2", "Os Exemplares", "Faixa 2")]
        with um.patch("spotifibr.runner.SpotifyClient", return_value=fake):
            txt, _ = run_links(cfg, log=lambda m: None)
        body = txt.read_text(encoding="utf-8")
        self.assertIn("2 música(s)", body)  # duplicata removida
        self.assertEqual(txt.name, "LINKS_PLAYLISTS.txt")
