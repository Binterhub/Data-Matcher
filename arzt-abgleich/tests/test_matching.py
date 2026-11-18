import io
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from openpyxl import load_workbook

from app import create_app, gender_from_name, gender_from_title, genders_differ
import learning
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


class GenderTests(unittest.TestCase):
    def test_title_and_first_name_genders(self):
        self.assertEqual(gender_from_title("Herr Dr."), "m")
        self.assertEqual(gender_from_title("Frau Dr."), "f")
        self.assertEqual(gender_from_title("OA Dr."), "m")
        self.assertEqual(gender_from_title("OÄ Dr."), "f")
        self.assertIsNone(gender_from_title("Dr."))
        self.assertEqual(gender_from_name("Anna Christina"), "f")
        self.assertEqual(gender_from_name("Thomas"), "m")
        self.assertIsNone(gender_from_name("Kim"))
        self.assertTrue(genders_differ("Dr.", "Anna", "Dr.", "Thomas"))
        self.assertTrue(genders_differ("Herr", "Anna", "Dr.", "Anna"))
        self.assertFalse(genders_differ("Dr.", "Anna", "OÄ Dr.", "Anna"))
        self.assertFalse(genders_differ("Dr.", "Kim", "Dr.", "Thomas"))
        self.assertFalse(genders_differ("Dr.", "Anna", "", ""))


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
            "K5": ("likely_wrong", "E1005", "fuzzy"),
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
        self.assertEqual(classify_score(75), "uncertain")
        self.assertEqual(classify_score(74), "likely_wrong")
        self.assertEqual(classify_score(60), "likely_wrong")
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

    def test_railway_volume_path_stores_the_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tmp
            try:
                create_app()
                self.assertTrue((Path(tmp) / "arzt.db").is_file())
            finally:
                os.environ.pop("RAILWAY_VOLUME_MOUNT_PATH", None)

    def test_export_keeps_columns_that_are_not_used_for_matching(self):
        self._login()
        payload = (
            "Kunden-ID,Vorname,Nachname,PLZ,Ort,Telefon,Website,E-Mail,Notiz\n"
            "K9,Ada,Lovelace,1010,Wien,0043111,https://ada.example,ada@example.com,Hinweis\n"
        )
        self.client.post(
            "/upload",
            data={
                "csrf_token": self._csrf(),
                "file": (io.BytesIO(payload.encode("utf-8")), "liste.csv"),
            },
            follow_redirects=True,
        )
        export = self.client.get("/uploads/1/export.xlsx")
        self.assertEqual(export.status_code, 200)
        workbook_bytes = io.BytesIO(export.data)
        header = next(load_workbook(workbook_bytes).active.iter_rows(values_only=True))
        self.assertIn("Telefon", header)
        self.assertIn("Website", header)
        self.assertIn("E-Mail", header)
        self.assertIn("Notiz", header)
        self.assertIn("Vorname", header)
        workbook_bytes.seek(0)
        row = list(load_workbook(workbook_bytes).active.iter_rows(values_only=True))[1]
        by_name = dict(zip(header, row))
        self.assertEqual(by_name["Telefon"], "0043111")
        self.assertEqual(by_name["Website"], "https://ada.example")
        self.assertEqual(by_name["E-Mail"], "ada@example.com")
        self.assertEqual(by_name["Notiz"], "Hinweis")
        self.assertEqual(by_name["Vorname"], "Ada")
        self.assertEqual(by_name["Nachname"], "Lovelace")

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
        self.assertIn("6 noch offen", html)
        self.assertIn("davon", html)
        self.assertIn("wahrscheinlich falsch", html)
        self.assertNotIn("von 2 offen", html)
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
        self.assertIn("5 noch offen", body)
        self.assertNotIn("1 von", body)
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


class LearningHintTests(unittest.TestCase):
    def test_second_given_name_does_not_lower_a_name_and_fach_match(self):
        hint = learning.hint_from_parts(
            ("Herr", "Philipp Max", "Trost", "1010", "Wien", "Innere Medizin"),
            ("Herr", "Philipp", "Trost", "4020", "Linz", "Innere Medizin"),
            counts={"philipp trost": 1},
        )
        self.assertEqual(hint["kind"], "right")
        self.assertIn("selten", hint["text"])
        self.assertIn("zweiter Vorname", hint["text"])
        self.assertIn("zählt nur wenig", hint["text"])
        self.assertNotIn("Geringe Sicherheit", hint["text"])

    def test_only_the_first_given_name_counts_as_a_mismatch(self):
        alignment = learning.name_alignment("Philipp Max", "Trost", "Max", "Trost")
        self.assertFalse(alignment["close"])
        hint = learning.hint_from_parts(
            ("Herr", "Philipp Max", "Trost", "1010", "Wien", "Innere Medizin"),
            ("Herr", "Max", "Trost", "1010", "Wien", "Innere Medizin"),
            counts={"max trost": 1, "philipp trost": 1},
        )
        self.assertEqual(hint["kind"], "down")
        self.assertIn("erster Vorname", hint["text"])

    def test_gender_mismatch_overrides_name_fach_and_rarity(self):
        hint = learning.hint_from_parts(
            ("Herr", "Philipp", "Trost", "1010", "Wien", "Innere Medizin"),
            ("Frau", "Philipp", "Trost", "1010", "Wien", "Innere Medizin"),
            counts={"philipp trost": 1},
        )
        self.assertEqual(hint["kind"], "low")
        self.assertIn("Geschlecht", hint["text"])
        self.assertNotIn("Hohe Sicherheit", hint["text"])

    def test_common_austrian_names_lower_a_good_name_and_fach_match(self):
        hint = learning.hint_from_parts(
            ("Herr", "Peter", "Huber", "1010", "Wien", "Innere Medizin"),
            ("Herr", "Peter", "Huber", "1010", "Wien", "Innere Medizin"),
            counts={"peter huber": 1},
        )
        self.assertEqual(hint["kind"], "caution")
        self.assertIn("häufig", hint["text"])

    def test_a_common_second_given_name_does_not_lower_confidence(self):
        hint = learning.hint_from_parts(
            ("Herr", "Xaver Peter", "Zingl", "1010", "Wien", "Innere Medizin"),
            ("Herr", "Xaver", "Zingl", "1010", "Wien", "Innere Medizin"),
            counts={"xaver zingl": 1},
        )
        self.assertEqual(hint["kind"], "right")
        self.assertNotIn("häufig", hint["text"])

    def test_fach_mismatch_outranks_a_matching_name_place_and_rarity(self):
        hint = learning.hint_from_parts(
            ("Herr", "Philipp", "Trost", "1010", "Wien", "Innere Medizin"),
            ("Herr", "Philipp", "Trost", "1010", "Wien", "Chirurgie"),
            counts={"philipp trost": 1},
        )
        self.assertEqual(hint["kind"], "down")
        self.assertIn("Fachgebiet", hint["text"])
        self.assertIn("seltener Name", hint["text"])
        self.assertIn("zählt nur wenig", hint["text"])

    def test_place_disagreement_does_not_downgrade_name_and_fach(self):
        hint = learning.hint_from_parts(
            ("Herr", "Philipp", "Trost", "1010", "Wien", "Innere Medizin"),
            ("Herr", "Philipp", "Trost", "5020", "Salzburg", "Innere Medizin"),
            counts={"philipp trost": 4},
        )
        self.assertEqual(hint["kind"], "right")
        self.assertIn("PLZ weicht ab", hint["text"])
        self.assertIn("Ort weicht ab", hint["text"])
        self.assertIn("zählt nur wenig", hint["text"])

    def test_hints_do_not_change_score_bands(self):
        self.assertEqual(classify_score(96), "very_likely")
        self.assertEqual(classify_score(88), "likely")
        self.assertEqual(classify_score(80), "uncertain")
        self.assertEqual(classify_score(70), "likely_wrong")
        self.assertEqual(classify_score(20), "unmatched")

    def test_learned_clause_follows_the_rule_and_stays_quiet_when_thin(self):
        features = learning.features_for(
            left_titel="Herr",
            left_vorname="Philipp",
            left_nachname="Trost",
            left_plz="1010",
            left_ort="Wien",
            left_fach="Innere Medizin",
            right_titel="Herr",
            right_vorname="Philipp",
            right_nachname="Trost",
            right_plz="1010",
            right_ort="Wien",
            right_fach="Innere Medizin",
            counts={"philipp trost": 1},
        )
        quiet = learning.hint_from_features(features, {"buckets": {"name_and_fach": {"n": 3, "accepts": 3}}})
        self.assertNotIn("Bisher", quiet["text"])
        loud = learning.hint_from_features(
            features,
            {"buckets": {"name_and_fach": {"n": 10, "accepts": 9}}},
        )
        self.assertIn("9 von 10", loud["text"])
        self.assertEqual(loud["kind"], "right")


if __name__ == "__main__":
    unittest.main()
