"""Normalize doctor fields and match an external row to one Referenzliste candidate."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from rapidfuzz import fuzz, process

LIKELY_MIN = 85
UNCERTAIN_MIN = 60
SUGGESTION_MIN = 40

_UMLAUTS = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "æ": "ae",
        "œ": "oe",
    }
)


def normalize_text(value) -> str:
    """Lowercase, fold umlauts, and turn punctuation into token separators."""
    if value is None:
        return ""
    text = str(value).strip().lower()
    if text in {"", "nan", "none", "nat"}:
        return ""
    text = text.translate(_UMLAUTS)
    text = re.sub(r"[-/'’`.]+", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_id(value) -> str:
    """Compact an ÖK or One-Key value so formatting differences still match."""
    text = normalize_text(value).replace(" ", "")
    for prefix in ("onekey", "oek"):
        rest = text[len(prefix) :]
        if text.startswith(prefix) and rest.isalnum() and any(ch.isdigit() for ch in rest):
            return rest
    return text


def normalize_plz(value) -> str:
    return re.sub(r"\D", "", "" if value is None else str(value))


def _token_blend(left: str, right: str) -> int:
    if not left or not right:
        return 0
    set_score = fuzz.token_set_ratio(left, right)
    sort_score = fuzz.token_sort_ratio(left, right)
    return int(round((set_score + sort_score) / 2))


def _first_name_score(left: str, right: str) -> int:
    score = _token_blend(left, right)
    left_tokens = left.split()
    right_tokens = right.split()
    if (
        len(left_tokens) == 1
        and len(left_tokens[0]) == 1
        and right_tokens
        and right_tokens[0].startswith(left_tokens[0])
    ):
        score = max(score, 70)
    if (
        len(right_tokens) == 1
        and len(right_tokens[0]) == 1
        and left_tokens
        and left_tokens[0].startswith(right_tokens[0])
    ):
        score = max(score, 70)
    return score


@dataclass
class Doctor:
    evo_id: str
    titel: str = ""
    vorname: str = ""
    nachname: str = ""
    ort: str = ""
    plz: str = ""
    hauptfach: str = ""
    oek: str = ""
    onekey: str = ""

    def __post_init__(self) -> None:
        self.evo_id = str(self.evo_id or "").strip()
        self.titel = _clean(self.titel)
        self.vorname = _clean(self.vorname)
        self.nachname = _clean(self.nachname)
        self.ort = _clean(self.ort)
        self.plz = _clean(self.plz)
        self.hauptfach = _clean(self.hauptfach)
        self.oek = _clean(self.oek)
        self.onekey = _clean(self.onekey)
        self.vorname_n = normalize_text(self.vorname)
        self.nachname_n = normalize_text(self.nachname)
        self.ort_n = normalize_text(self.ort)
        self.plz_n = normalize_plz(self.plz)
        self.fach_n = normalize_text(self.hauptfach)
        self.oek_n = normalize_id(self.oek)
        self.onekey_n = normalize_id(self.onekey)


@dataclass
class ExternalPerson:
    vorname: str = ""
    nachname: str = ""
    ort: str = ""
    plz: str = ""
    hauptfach: str = ""
    oek: str = ""
    onekey: str = ""
    titel: str = ""

    def __post_init__(self) -> None:
        self.titel = _clean(self.titel)
        self.vorname = _clean(self.vorname)
        self.nachname = _clean(self.nachname)
        self.ort = _clean(self.ort)
        self.plz = _clean(self.plz)
        self.hauptfach = _clean(self.hauptfach)
        self.oek = _clean(self.oek)
        self.onekey = _clean(self.onekey)
        self.vorname_n = normalize_text(self.vorname)
        self.nachname_n = normalize_text(self.nachname)
        self.ort_n = normalize_text(self.ort)
        self.plz_n = normalize_plz(self.plz)
        self.fach_n = normalize_text(self.hauptfach)
        self.oek_n = normalize_id(self.oek)
        self.onekey_n = normalize_id(self.onekey)


@dataclass
class MatchResult:
    evo_id: str | None
    score: int
    status: str
    method: str
    note: str = ""
    titel: str = ""
    vorname: str = ""
    nachname: str = ""
    ort: str = ""
    plz: str = ""
    hauptfach: str = ""
    oek: str = ""
    onekey: str = ""


def _clean(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "nat"}:
        return ""
    return text


def _from_doctor(doctor: Doctor | None, score: int, status: str, method: str, note: str) -> MatchResult:
    if doctor is None:
        return MatchResult(evo_id=None, score=score, status=status, method=method, note=note)
    return MatchResult(
        evo_id=doctor.evo_id,
        score=score,
        status=status,
        method=method,
        note=note,
        titel=doctor.titel,
        vorname=doctor.vorname,
        nachname=doctor.nachname,
        ort=doctor.ort,
        plz=doctor.plz,
        hauptfach=doctor.hauptfach,
        oek=doctor.oek,
        onekey=doctor.onekey,
    )


def name_parts(person, doctor: Doctor) -> tuple[int, int]:
    last = _token_blend(person.nachname_n, doctor.nachname_n)
    if person.vorname_n and doctor.vorname_n:
        first = _first_name_score(person.vorname_n, doctor.vorname_n)
        return int(round(0.65 * last + 0.35 * first)), last
    return last, last


def address_score(person, doctor: Doctor) -> tuple[int, bool]:
    has_plz = bool(person.plz_n and doctor.plz_n)
    has_ort = bool(person.ort_n and doctor.ort_n)
    plz_score = 100 if has_plz and person.plz_n == doctor.plz_n else (0 if has_plz else None)
    ort_score = fuzz.ratio(person.ort_n, doctor.ort_n) if has_ort else None
    if plz_score is None and ort_score is None:
        return 0, False
    if plz_score is None:
        return int(ort_score), True
    if ort_score is None:
        return int(plz_score), True
    return int(round(0.7 * plz_score + 0.3 * ort_score)), True


def specialty_score(person, doctor: Doctor) -> tuple[int, bool]:
    if not person.fach_n or not doctor.fach_n:
        return 0, False
    return _token_blend(person.fach_n, doctor.fach_n), True


def combined_score(person, doctor: Doctor) -> int:
    """Weighted percentage. Missing specialty or address is left out and the rest is rescaled."""
    components: list[tuple[int, float]] = []
    name, _last = name_parts(person, doctor)
    components.append((name, 0.60))
    address, has_address = address_score(person, doctor)
    specialty, has_specialty = specialty_score(person, doctor)
    if has_address:
        components.append((address, 0.25))
    if has_specialty:
        components.append((specialty, 0.15))
    weight = sum(item[1] for item in components)
    if weight <= 0:
        return 0
    return int(round(sum(score * item_weight for score, item_weight in components) / weight))


def classify_score(score: int) -> str:
    if score >= LIKELY_MIN:
        return "likely"
    if score >= UNCERTAIN_MIN:
        return "uncertain"
    return "unmatched"


class Matcher:
    def __init__(self, doctors: list[Doctor]) -> None:
        self.doctors = doctors
        self.by_oek: dict[str, Doctor] = {}
        self.by_onekey: dict[str, Doctor] = {}
        self.by_plz: dict[str, list[Doctor]] = defaultdict(list)
        self.by_token: dict[str, list[Doctor]] = defaultdict(list)
        self.duplicate_ids: list[str] = []
        for doctor in doctors:
            if doctor.oek_n:
                if doctor.oek_n in self.by_oek:
                    self.duplicate_ids.append(f"ÖK {doctor.oek}")
                else:
                    self.by_oek[doctor.oek_n] = doctor
            if doctor.onekey_n:
                if doctor.onekey_n in self.by_onekey:
                    self.duplicate_ids.append(f"One-Key {doctor.onekey}")
                else:
                    self.by_onekey[doctor.onekey_n] = doctor
            if doctor.plz_n:
                self.by_plz[doctor.plz_n].append(doctor)
            for token in doctor.nachname_n.split():
                if len(token) >= 3:
                    self.by_token[token].append(doctor)

    def match(self, person: ExternalPerson) -> MatchResult:
        oek_hit = self.by_oek.get(person.oek_n) if person.oek_n else None
        key_hit = self.by_onekey.get(person.onekey_n) if person.onekey_n else None
        if oek_hit and key_hit and oek_hit.evo_id != key_hit.evo_id:
            return _from_doctor(
                oek_hit,
                100,
                "uncertain",
                "conflict",
                "ÖK- und One-Key-Nummer zeigen auf unterschiedliche Evo-IDs.",
            )
        if oek_hit:
            return _from_doctor(oek_hit, 100, "auto", "oek", "Exakte ÖK-Nummer.")
        if key_hit:
            return _from_doctor(key_hit, 100, "auto", "onekey", "Exakte One-Key-Nummer.")

        candidates: list[Doctor] = []
        seen: set[str] = set()

        def add(doctor: Doctor) -> None:
            if doctor.evo_id not in seen:
                seen.add(doctor.evo_id)
                candidates.append(doctor)

        if person.plz_n:
            for doctor in self.by_plz.get(person.plz_n, []):
                add(doctor)
        for token in person.nachname_n.split():
            if len(token) >= 3:
                for doctor in self.by_token.get(token, []):
                    add(doctor)
        if person.nachname_n and self.doctors:
            choices = [doctor.nachname_n for doctor in self.doctors]
            hits = process.extract(
                person.nachname_n,
                choices,
                scorer=fuzz.token_set_ratio,
                limit=5,
                score_cutoff=70,
            )
            for _choice, _score, index in hits:
                add(self.doctors[index])

        best: Doctor | None = None
        best_key = (-1, -1, -1)
        for doctor in candidates:
            score = combined_score(person, doctor)
            name, _last = name_parts(person, doctor)
            address, _has_address = address_score(person, doctor)
            key = (score, name, address)
            if key > best_key:
                best_key = key
                best = doctor

        if best is None:
            return _from_doctor(None, 0, "unmatched", "none", "Kein Kandidat.")

        score = best_key[0]
        if score < SUGGESTION_MIN:
            return _from_doctor(None, score, "unmatched", "none", "Unter der Schwelle.")

        status = classify_score(score)
        note = ""
        identifier_missing = (person.oek_n and not oek_hit) or (person.onekey_n and not key_hit)
        if identifier_missing and status == "likely":
            status = "uncertain"
            note = "Kennung steht nicht in der Referenzliste."
        elif status == "unmatched":
            note = "Bester Kandidat liegt unter der Unsicher-Schwelle."
        return _from_doctor(best, score, status, "fuzzy", note)


def search_doctors(doctors: list[Doctor], query: str, limit: int = 8) -> list[tuple[int, Doctor]]:
    text = query.strip()
    if len(text) < 2:
        return []
    folded = normalize_text(text)
    compact = normalize_id(text)
    ranked: list[tuple[int, Doctor]] = []
    for doctor in doctors:
        if text.casefold() == doctor.evo_id.casefold():
            ranked.append((100, doctor))
            continue
        if compact and compact in {doctor.oek_n, doctor.onekey_n}:
            ranked.append((100, doctor))
            continue
        name = normalize_text(f"{doctor.vorname} {doctor.nachname} {doctor.ort}")
        score = fuzz.WRatio(folded, name)
        if score >= 60:
            ranked.append((int(score), doctor))
    ranked.sort(key=lambda item: (-item[0], item[1].nachname, item[1].vorname))
    return ranked[:limit]


def manual_result(doctor: Doctor, note: str) -> MatchResult:
    return _from_doctor(doctor, 100, "manual", "manual", note)
