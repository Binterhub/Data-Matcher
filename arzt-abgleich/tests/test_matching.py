import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from openpyxl import load_workbook

from app import create_app
from matching import (
    Doctor,
    ExternalPerson,
    Matcher,
    classify_score,
    normalize_id,
    normalize_text,
)
from tables import parse_external, parse_reference, read_table

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"


def doctors_from_sample() -> list[Doctor]:
    frame = read_table("referenzliste.csv", (SAMPLES / "referenzliste.csv").read_bytes())
    parsed, _log, skipped = parse_reference(frame)
    assert skipped == 1
    return [Doctor(**row) for row in parsed]


class NormalizeTests(unittest.TestCase):
    def test_umlauts_and_punctuation(self):
        self.assertEqual(normalize_text("Müller-Schmidt!"), "mueller schmidt")
        self.assertEqual(normalize_text("Größe / ÖÄÜ"), "groesse oeaeue")
        self.assertEqual(normalize_id("ÖK 123-456"), "123456")
        self.assertEqual(normalize_id("W-1003"), "w1003")


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.matcher = Matcher(doctors_from_sample())

    def _person(self, **kwargs) -> ExternalPerson:
        return ExternalPerson(**kwargs)

    def test_sample_rows_land_in_expected_groups(self):
        frame = read_table("externe_liste.csv", (SAMPLES / "externe_liste.csv").read_bytes())
        rows, columns, _log = parse_external(frame)
        self.assertEqual(columns, ["Kunden-ID"])
        expected = {
            "K1": ("auto", "E1001", "oek"),
            "K2": ("very_likely", "E1002", "fuzzy"),
            "K3": ("auto", "E1003", "onekey"),
            "K4": ("very_likely", "E1004", "fuzzy"),
            "K5": ("uncertain", "E1005", "fuzzy"),
            "K6": ("unmatched", None, "none"),
        }
        self.assertEqual(len(rows), len(expected))
        for row in rows:
            result = self.matcher.match(self._person(**{key: row[key] for key in ("titel", "vorname", "nachname", "ort", "plz", "hauptfach", "oek", "onekey")}))
            status, evo_id, method = expected[row["customer_ids"]["Kunden-ID"]]
            self.assertEqual(result.status, status, row["customer_ids"])
            self.assertEqual(result.evo_id, evo_id, row["customer_ids"])
            self.assertEqual(result.method, method, row["customer_ids"])
            if status == "very_likely":
                self.assertGreaterEqual(result.score, 92)
            if status == "likely":
                self.assertGreaterEqual(result.score, 85)
                self.assertLess(result.score, 92)
            if status == "auto":
                self.assertEqual(result.score, 100)

    def test_score_bands(self):
        self.assertEqual(classify_score(100), "very_likely")
        self.assertEqual(classify_score(92), "very_likely")
        self.assertEqual(classify_score(91), "likely")
        self.assertEqual(classify_score(85), "likely")
        self.assertEqual(classify_score(84), "uncertain")
        self.assertEqual(classify_score(60), "uncertain")
        self.assertEqual(classify_score(59), "likely_wrong")
        self.assertEqual(classify_score(40), "likely_wrong")
        self.assertEqual(classify_score(39), "unmatched")

    def test_middle_and_low_bands_keep_the_candidate(self):
        likely = self.matcher.match(
            ExternalPerson(vorname="Anna", nachname="Huber", plz="1010", ort="Wien", hauptfach="Chirurgie")
        )
        self.assertEqual(likely.status, "likely")
        self.assertEqual(likely.evo_id, "E1001")
        self.assertEqual(likely.score, 89)

        wrong = self.matcher.match(
            ExternalPerson(vorname="Erika", nachname="Wagner", plz="2700", ort="Wiener Neustadt", hauptfach="HNO")
        )
        self.assertEqual(wrong.status, "likely_wrong")
        self.assertEqual(wrong.method, "fuzzy")
        self.assertEqual(wrong.evo_id, "E1006")
        self.assertEqual(wrong.score, 55)
        self.assertIn("Unsicher-Schwelle", wrong.note)

    def test_missing_identifier_caps_a_high_score(self):
        result = self.matcher.match(
            ExternalPerson(
                vorname="Maria",
                nachname="Berger",
                plz="4020",
                ort="Linz",
                hauptfach="Kinderheilkunde",
                oek="000111",
            )
        )
        self.assertEqual(result.score, 100)
        self.assertEqual(result.status, "uncertain")
        self.assertEqual(result.evo_id, "E1003")

    def test_conflicting_identifiers_are_not_auto_mapped(self):
        result = self.matcher.match(
            ExternalPerson(vorname="Anna", nachname="Huber", oek="123456", onekey="W1002")
        )
        self.assertEqual(result.status, "uncertain")
        self.assertEqual(result.method, "conflict")
        self.assertEqual(result.evo_id, "E1001")

    def test_only_best_candidate_is_returned(self):
        result = self.matcher.match(
            ExternalPerson(vorname="Anna", nachname="Huber", plz="1010", ort="Wien", hauptfach="Innere Medizin")
        )
        self.assertEqual(result.evo_id, "E1001")
        self.assertGreaterEqual(result.score, 85)


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(self.tmp.name)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def _csrf(self) -> str:
        with self.client.session_transaction() as stored:
            return stored["csrf_token"]

    def _login(self):
        self.client.get("/setup")
        response = self.client.post(
            "/setup",
            data={"csrf_token": self._csrf(), "username": "arztadmin", "password": "korrektes-passwort"},
            follow_redirects=True,
        )
        self.assertIn("Anmelden".encode(), response.data)
        response = self.client.post(
            "/login",
            data={"csrf_token": self._csrf(), "username": "arztadmin", "password": "falsch"},
        )
        self.assertIn("fehlgeschlagen".encode(), response.data)
        self.client.post(
            "/login",
            data={"csrf_token": self._csrf(), "username": "arztadmin", "password": "korrektes-passwort"},
            follow_redirects=True,
        )

    def test_upload_review_override_and_export(self):
        self._login()
        self.client.post(
            "/referenz",
            data={
                "csrf_token": self._csrf(),
                "file": (io.BytesIO((SAMPLES / "referenzliste.csv").read_bytes()), "referenzliste.csv"),
            },
            follow_redirects=True,
        )
        response = self.client.post(
            "/upload",
            data={
                "csrf_token": self._csrf(),
                "file": (io.BytesIO((SAMPLES / "externe_liste.csv").read_bytes()), "externe_liste.csv"),
            },
            follow_redirects=True,
        )
        page = response.data.decode()
        self.assertIn("Automatisch", page)
        self.assertIn("Sehr wahrscheinlich", page)
        self.assertIn("Wahrscheinlich falsch", page)
        self.assertIn("E1001", page)
        self.assertIn("E1002", page)
        self.assertIn("Kein Treffer", page)
        self.assertNotIn("Doppelt Eintrag", page)
        self.assertIn('name="band" value="very_likely"', page)

        workbook_bytes = io.BytesIO()
        export = self.client.get("/uploads/1/export.xlsx")
        self.assertEqual(export.status_code, 200)
        workbook_bytes.write(export.data)
        workbook_bytes.seek(0)
        sheet = load_workbook(workbook_bytes).active
        exported = list(sheet.iter_rows(values_only=True))
        header = exported[0]
        self.assertIn("Evo-ID", header)
        self.assertIn("Kunden-ID", header)
        evo_index = header.index("Evo-ID")
        id_index = header.index("Kunden-ID")
        by_customer = {row[id_index]: row[evo_index] for row in exported[1:]}
        self.assertEqual(by_customer["K1"], "E1001")
        self.assertEqual(by_customer["K6"], None)

        csv_export = self.client.get("/uploads/1/export.csv")
        self.assertIn("K2", csv_export.data.decode("utf-8-sig"))

        self.client.post(
            "/uploads/1/rows/6/assign",
            data={"csrf_token": self._csrf(), "evo_id": "E1006"},
            follow_redirects=True,
        )
        csv_export = self.client.get("/uploads/1/export.csv").data.decode("utf-8-sig")
        self.assertIn("Manuell", csv_export)
        self.assertIn("E1006", csv_export)

    def _upload_samples(self):
        self._login()
        self.client.post(
            "/referenz",
            data={
                "csrf_token": self._csrf(),
                "file": (io.BytesIO((SAMPLES / "referenzliste.csv").read_bytes()), "referenzliste.csv"),
            },
            follow_redirects=True,
        )
        self.client.post(
            "/upload",
            data={
                "csrf_token": self._csrf(),
                "file": (io.BytesIO((SAMPLES / "externe_liste.csv").read_bytes()), "externe_liste.csv"),
            },
            follow_redirects=True,
        )

    def test_accept_and_reject_open_the_next_row_in_the_same_band(self):
        self._upload_samples()
        page = self.client.get("/uploads/1?band=very_likely")
        html = page.data.decode()
        self.assertIn("Zur Liste", html)
        self.assertIn("Mueller Schmidt", html)
        self.assertNotIn('id="uncertain"', html)
        accept = re.search(r'action="([^"]+/accept[^"]*)"', html)
        self.assertIsNotNone(accept)
        response = self.client.post(
            accept.group(1),
            data={"csrf_token": self._csrf(), "band": "very_likely"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        location = response.headers["Location"]
        self.assertIn("band=very_likely", location)
        self.assertIn("row=", location)
        self.assertNotRegex(location, r"/uploads/1$")
        followed = self.client.get(location)
        body = followed.data.decode()
        self.assertIn("Gruber", body)
        self.assertNotIn("Mueller Schmidt", body)
        self.assertIn("Zur Liste", body)
        reject = re.search(r'action="([^"]+/reject[^"]*)"', body)
        self.assertIsNotNone(reject)
        response = self.client.post(
            reject.group(1),
            data={"csrf_token": self._csrf(), "band": "very_likely"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        done_location = response.headers["Location"]
        self.assertIn("band=very_likely", done_location)
        self.assertIn("done=1", done_location)
        done = self.client.get(done_location)
        done_html = done.data.decode()
        self.assertIn("Keine weitere offene Zeile", done_html)
        self.assertNotIn('id="auto"', done_html)

    def test_excel_reference_roundtrip(self):
        frame = pd.read_csv(SAMPLES / "referenzliste.csv", dtype=str, keep_default_na=False)
        buffer = io.BytesIO()
        frame.to_excel(buffer, index=False)
        parsed, log, skipped = parse_reference(read_table("referenz.xlsx", buffer.getvalue()))
        self.assertEqual(skipped, 1)
        self.assertEqual(len(parsed), 6)
        self.assertIn("doppelte Evo-ID", log)


if __name__ == "__main__":
    unittest.main()
