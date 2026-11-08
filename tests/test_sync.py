import json
import tempfile
import unittest
from pathlib import Path

from trex_sync.library import Library, LocalFile, normalize
from trex_sync.spotify import Track, parse_playlist_id, track_from_json
from trex_sync.sync import TRANSFER_DIR, State, confirm_transfer, sync_playlist, write_missing


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
        from trex_sync.sync import run_downloader
        import unittest.mock as um
        with um.patch("subprocess.run") as run:
            run_downloader(["x", "{dir}/{artist}.{output-ext}"], T("7", "A", "B"), dl)
            self.assertEqual(run.call_args[0][0], ["x", f"{dl}/A.{{output-ext}}"])
        r = sync_playlist("p2", "Y", [T("7", "Novo", "Single")], self.lib(), self.state, self.out,
                          downloader=cmd, download_dir=dl)
        self.assertEqual(r.new, ["Novo - Single.mp3"])


if __name__ == "__main__":
    unittest.main()
