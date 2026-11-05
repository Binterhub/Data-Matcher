"""Card hints from decisions and name patterns.

This layer never changes match scores or band thresholds. It only describes
how strong a suggestion looks, using a fixed ranking:

1. Gender mismatch — strongest downgrade, outweighs everything else.
2. Name and Fachgebiet — next, and a mismatch here downgrades hard.
   Only the first given name and the last name count. An extra or different
   second given name does not.
3. Name rarity — a rare first-name + last-name pair raises confidence, a
   common one (including Peter, Thomas, Michael, Kober, Huber, Meier) lowers it.
4. PLZ and city — weak. They never overturn a stronger signal.
"""

from __future__ import annotations

import json

from rapidfuzz import fuzz

import db
from matching import normalize_plz, normalize_text

COMMON_FIRST = frozenset({"peter", "thomas", "michael"})
COMMON_LAST = frozenset({"kober", "huber", "meier"})
CLOSE_MIN = 88
FACH_MIN = 88
RARE_MAX = 1
COMMON_COUNT_MIN = 8
LEARNED_MIN = 8

_STATE: dict = {"version": None, "counts": None, "stats": {}}


def first_given(vorname: str) -> str:
    parts = normalize_text(vorname).split()
    return parts[0] if parts else ""


def identity_key(vorname: str, nachname: str) -> str:
    first = first_given(vorname)
    last = normalize_text(nachname)
    return f"{first} {last}".strip()


def carries_common_name(vorname: str, nachname: str) -> bool:
    """Common Austrian names lower confidence. Only the first given name counts."""
    if first_given(vorname) in COMMON_FIRST:
        return True
    return any(token in COMMON_LAST for token in normalize_text(nachname).split())


def name_alignment(left_vorname: str, left_nachname: str, right_vorname: str, right_nachname: str) -> dict:
    """First given name plus last name. Further given names are ignored."""
    left_first = first_given(left_vorname)
    right_first = first_given(right_vorname)
    left_last = normalize_text(left_nachname)
    right_last = normalize_text(right_nachname)
    close = _close(left_first, right_first) and _close(left_last, right_last)
    left_extra = normalize_text(left_vorname).split()[1:]
    right_extra = normalize_text(right_vorname).split()[1:]
    return {"close": close, "extra_given": close and left_extra != right_extra}


def fach_agrees(left: str, right: str) -> bool | None:
    left_n = normalize_text(left)
    right_n = normalize_text(right)
    if not left_n or not right_n:
        return None
    if left_n == right_n:
        return True
    return fuzz.token_set_ratio(left_n, right_n) >= FACH_MIN


def _close(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    return fuzz.ratio(left, right) >= CLOSE_MIN


def _known_equal(left: str, right: str, normalize) -> bool | None:
    left_n = normalize(left)
    right_n = normalize(right)
    if not left_n or not right_n:
        return None
    return left_n == right_n


def _rarity(left_key: str, right_key: str, counts: dict[str, int] | None) -> str:
    if not counts:
        return "unknown"
    highest = max(counts.get(left_key, 0), counts.get(right_key, 0))
    if highest >= COMMON_COUNT_MIN:
        return "common"
    if highest <= RARE_MAX:
        return "rare"
    return "typical"


def _gender_mismatch(left_titel: str, left_vorname: str, right_titel: str, right_vorname: str) -> bool:
    from app import genders_differ

    return genders_differ(left_titel, left_vorname, right_titel, right_vorname)


def features_for(
    *,
    left_titel: str,
    left_vorname: str,
    left_nachname: str,
    left_plz: str,
    left_ort: str,
    left_fach: str,
    right_titel: str,
    right_vorname: str,
    right_nachname: str,
    right_plz: str,
    right_ort: str,
    right_fach: str,
    score: int = 0,
    status: str = "",
    counts: dict[str, int] | None = None,
    compared: bool = True,
) -> dict:
    alignment = name_alignment(left_vorname, left_nachname, right_vorname, right_nachname)
    common = carries_common_name(left_vorname, left_nachname) or carries_common_name(
        right_vorname, right_nachname
    )
    rarity = _rarity(
        identity_key(left_vorname, left_nachname),
        identity_key(right_vorname, right_nachname),
        counts,
    )
    if common and rarity == "rare":
        rarity = "typical"
    return {
        "compared": compared,
        "gender_mismatch": compared
        and _gender_mismatch(left_titel, left_vorname, right_titel, right_vorname),
        "name_close": bool(alignment["close"]) if compared else False,
        "extra_given": bool(alignment["extra_given"]) if compared else False,
        "fach_same": fach_agrees(left_fach, right_fach) if compared else None,
        "common_name": common if compared else False,
        "rarity": rarity if compared else "unknown",
        "plz_same": _known_equal(left_plz, right_plz, normalize_plz) if compared else None,
        "city_same": _known_equal(left_ort, right_ort, normalize_text) if compared else None,
        "score": int(score or 0),
        "status": status or "",
    }


def features_from_stored(row, counts: dict[str, int] | None) -> dict:
    compared = bool(row["match_evo_id"])
    return features_for(
        left_titel=row["titel"],
        left_vorname=row["vorname"],
        left_nachname=row["nachname"],
        left_plz=row["plz"],
        left_ort=row["ort"],
        left_fach=row["hauptfach"],
        right_titel=row["match_titel"] if compared else "",
        right_vorname=row["match_vorname"] if compared else "",
        right_nachname=row["match_nachname"] if compared else "",
        right_plz=row["match_plz"] if compared else "",
        right_ort=row["match_ort"] if compared else "",
        right_fach=row["match_hauptfach"] if compared else "",
        score=row["match_score"],
        status=row["match_status"],
        counts=counts,
        compared=compared,
    )


def features_from_result(row, result, counts: dict[str, int] | None) -> dict:
    compared = bool(result and result.evo_id)
    return features_for(
        left_titel=row["titel"],
        left_vorname=row["vorname"],
        left_nachname=row["nachname"],
        left_plz=row["plz"],
        left_ort=row["ort"],
        left_fach=row["hauptfach"],
        right_titel=result.titel if compared else "",
        right_vorname=result.vorname if compared else "",
        right_nachname=result.nachname if compared else "",
        right_plz=result.plz if compared else "",
        right_ort=result.ort if compared else "",
        right_fach=result.hauptfach if compared else "",
        score=result.score if result else 0,
        status=result.status if result else "",
        counts=counts,
        compared=compared,
    )


def summarize(examples: list[tuple[str, dict]]) -> dict:
    keys = (
        "gender_mismatch",
        "name_and_fach_mismatch",
        "name_mismatch",
        "fach_mismatch",
        "name_and_fach",
        "common_name",
        "rare_name",
        "extra_given",
        "plz_mismatch",
        "city_mismatch",
    )
    buckets = {key: {"n": 0, "accepts": 0} for key in keys}

    def add(key: str, accepted: bool) -> None:
        buckets[key]["n"] += 1
        if accepted:
            buckets[key]["accepts"] += 1

    for decision, features in examples:
        if not features.get("compared"):
            continue
        accepted = decision == "accept"
        if features.get("gender_mismatch"):
            add("gender_mismatch", accepted)
        if features.get("name_close") and features.get("fach_same") is True:
            add("name_and_fach", accepted)
        if features.get("name_close") is False:
            add("name_mismatch", accepted)
        if features.get("fach_same") is False:
            add("fach_mismatch", accepted)
        if features.get("name_close") is False and features.get("fach_same") is False:
            add("name_and_fach_mismatch", accepted)
        if features.get("common_name") or features.get("rarity") == "common":
            add("common_name", accepted)
        if features.get("rarity") == "rare" and not features.get("common_name"):
            add("rare_name", accepted)
        if features.get("extra_given"):
            add("extra_given", accepted)
        if features.get("plz_same") is False:
            add("plz_mismatch", accepted)
        if features.get("city_same") is False:
            add("city_mismatch", accepted)
    return {"n": len(examples), "buckets": buckets}


def hint_from_features(features: dict, stats: dict | None = None) -> dict | None:
    if not features.get("compared"):
        return None
    kind, text = _rule_hint(features)
    if not text:
        return None
    clause = _learned_clause(features, stats or {}, kind)
    if clause:
        text = f"{text} {clause}"
    return {"kind": kind, "text": text}


def hint_from_parts(left: tuple, right: tuple, counts: dict[str, int] | None = None, stats: dict | None = None) -> dict | None:
    """left/right: titel, vorname, nachname, plz, ort, hauptfach."""
    features = features_for(
        left_titel=left[0],
        left_vorname=left[1],
        left_nachname=left[2],
        left_plz=left[3],
        left_ort=left[4],
        left_fach=left[5],
        right_titel=right[0],
        right_vorname=right[1],
        right_nachname=right[2],
        right_plz=right[3],
        right_ort=right[4],
        right_fach=right[5],
        counts=counts,
    )
    return hint_from_features(features, stats)


def hint_for_row(row) -> dict | None:
    counts = _STATE["counts"] or {}
    return hint_from_features(features_from_stored(row, counts), _STATE["stats"])


def prepare(connection, rematch_factory=None) -> dict:
    _ensure_table(connection)
    _counts(connection)
    _backfill(connection, rematch_factory)
    _STATE["stats"] = _stats_from_db(connection)
    return _STATE["stats"]


def remember(connection, row, decision: str) -> None:
    _ensure_table(connection)
    counts = _counts(connection)
    db.save_decision(
        connection,
        row["id"],
        row["upload_id"],
        decision,
        features_from_stored(row, counts),
    )
    _STATE["stats"] = _stats_from_db(connection)


def remember_assignment(connection, row, doctor) -> None:
    _ensure_table(connection)
    counts = _counts(connection)
    features = features_for(
        left_titel=row["titel"],
        left_vorname=row["vorname"],
        left_nachname=row["nachname"],
        left_plz=row["plz"],
        left_ort=row["ort"],
        left_fach=row["hauptfach"],
        right_titel=doctor["titel"],
        right_vorname=doctor["vorname"],
        right_nachname=doctor["nachname"],
        right_plz=doctor["plz"],
        right_ort=doctor["ort"],
        right_fach=doctor["hauptfach"],
        score=100,
        status="manual",
        counts=counts,
    )
    db.save_decision(connection, row["id"], row["upload_id"], "accept", features)
    _STATE["stats"] = _stats_from_db(connection)


def forget(connection, row_id: int) -> None:
    _ensure_table(connection)
    db.delete_decision(connection, row_id)
    _STATE["stats"] = _stats_from_db(connection)


def _rule_hint(features: dict) -> tuple[str, str]:
    if features.get("gender_mismatch"):
        return (
            "low",
            "Sehr geringe Sicherheit: Geschlecht weicht ab. "
            "Das wiegt stärker als Name, Fachgebiet und Adresse.",
        )

    name_close = bool(features.get("name_close"))
    fach = features.get("fach_same")
    if not name_close and fach is False:
        return "down", _with_notes("Geringe Sicherheit: Name und Fachgebiet weichen ab.", features)
    if not name_close and fach is True:
        return (
            "down",
            _with_notes(
                "Geringe Sicherheit: erster Vorname oder Nachname weicht ab. "
                "Das Fachgebiet passt, wiegt hier aber weniger.",
                features,
            ),
        )
    if not name_close:
        return "down", _with_notes(
            "Geringe Sicherheit: erster Vorname oder Nachname weicht ab.",
            features,
        )
    if fach is False:
        rare = ""
        if features.get("rarity") == "rare" and not features.get("common_name"):
            rare = " Auch ein seltener Name ändert das nicht."
        return (
            "down",
            _with_notes(
                "Geringe Sicherheit: das Fachgebiet weicht ab. "
                "Der Name passt, wiegt das aber nicht auf." + rare,
                features,
            ),
        )
    if fach is True and (features.get("common_name") or features.get("rarity") == "common"):
        return (
            "caution",
            _with_notes(
                "Geringere Sicherheit: Name und Fachgebiet passen, der Name ist aber sehr häufig.",
                features,
            ),
        )
    if fach is True and features.get("rarity") == "rare":
        return (
            "right",
            _with_notes(
                "Hohe Sicherheit: Name und Fachgebiet passen, und der Name ist selten.",
                features,
            ),
        )
    if fach is True:
        return "right", _with_notes("Hohe Sicherheit: Name und Fachgebiet passen.", features)
    if features.get("rarity") == "rare" and not features.get("common_name"):
        return (
            "minor",
            _with_notes("Name passt und ist selten. Ohne Fachgebiet keine hohe Sicherheit.", features),
        )
    if features.get("common_name") or features.get("rarity") == "common":
        return (
            "caution",
            _with_notes(
                "Geringere Sicherheit: der Name ist sehr häufig, und das Fachgebiet fehlt.",
                features,
            ),
        )
    if features.get("plz_same") is False or features.get("city_same") is False:
        return "minor", _with_notes("PLZ oder Ort weichen ab.", features, place=False)
    if features.get("plz_same") is True or features.get("city_same") is True:
        return "minor", _with_notes("PLZ oder Ort passen.", features, place=False)
    return "", ""


def _with_notes(base: str, features: dict, place: bool = True) -> str:
    text = base.rstrip()
    if features.get("name_close") and features.get("extra_given"):
        text += " Ein zweiter Vorname, der fehlt oder abweicht, senkt die Sicherheit nicht."
    if place:
        text += _place_clause(features.get("plz_same"), features.get("city_same"))
    elif features.get("plz_same") is not None or features.get("city_same") is not None:
        text += " Das zählt nur wenig."
    return text


def _place_clause(plz_same, city_same) -> str:
    bits = []
    if plz_same is True:
        bits.append("PLZ passt")
    elif plz_same is False:
        bits.append("PLZ weicht ab")
    if city_same is True:
        bits.append("Ort passt")
    elif city_same is False:
        bits.append("Ort weicht ab")
    if not bits:
        return ""
    return " " + " und ".join(bits) + " — das zählt nur wenig."


def _learned_clause(features: dict, stats: dict, kind: str) -> str:
    buckets = (stats or {}).get("buckets") or {}
    if kind == "low":
        key = "gender_mismatch"
        expect_low = True
    elif kind == "down":
        expect_low = True
        if features.get("name_close") is False and features.get("fach_same") is False:
            key = "name_and_fach_mismatch"
        elif features.get("name_close") is False:
            key = "name_mismatch"
        else:
            key = "fach_mismatch"
    elif kind == "caution":
        key = "common_name"
        expect_low = True
    elif kind == "right":
        key = "name_and_fach"
        expect_low = False
    elif features.get("plz_same") is False:
        key = "plz_mismatch"
        expect_low = True
    else:
        return ""
    bucket = buckets.get(key) or {}
    total = bucket.get("n") or 0
    if total < LEARNED_MIN:
        return ""
    accepts = bucket.get("accepts") or 0
    rate = accepts / total
    if expect_low and rate > 0.35:
        return ""
    if not expect_low and rate < 0.65:
        return ""
    return f"Bisher {accepts} von {total} ähnlichen Fällen übernommen."


def _ensure_table(connection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS decision_examples (
            row_id INTEGER PRIMARY KEY,
            upload_id INTEGER NOT NULL,
            decision TEXT NOT NULL,
            features TEXT NOT NULL,
            decided_at TEXT NOT NULL
        )"""
    )
    connection.commit()


def _counts(connection) -> dict[str, int]:
    version = db.current_version(connection)
    version_id = version["id"] if version else None
    listed = connection.execute("PRAGMA database_list").fetchone()
    cache_key = (listed["file"] if listed else "", version_id)
    if _STATE["counts"] is not None and _STATE["version"] == cache_key:
        return _STATE["counts"]
    counts: dict[str, int] = {}
    if version_id is not None:
        for doctor in db.load_doctors(connection, version_id):
            key = identity_key(doctor["vorname"], doctor["nachname"])
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
    _STATE["version"] = cache_key
    _STATE["counts"] = counts
    return counts


def _backfill(connection, rematch_factory) -> None:
    missing = db.locked_rows_without_decision(connection)
    if not missing:
        return
    needs_result = [row for row in missing if not row["match_evo_id"]]
    rematch = rematch_factory() if needs_result and rematch_factory else None
    counts = _counts(connection)
    for row in missing:
        note = (row["match_note"] or "").lower()
        rejected = "verworfen" in note or not row["match_evo_id"]
        if row["match_evo_id"] and not rejected:
            features = features_from_stored(row, counts)
            decision = "accept"
        elif rematch is not None:
            features = features_from_result(row, rematch(row), counts)
            decision = "reject"
        elif row["match_evo_id"]:
            features = features_from_stored(row, counts)
            decision = "reject" if rejected else "accept"
        else:
            continue
        db.save_decision(connection, row["id"], row["upload_id"], decision, features)


def _stats_from_db(connection) -> dict:
    examples = []
    for row in db.list_decisions(connection):
        examples.append((row["decision"], json.loads(row["features"])))
    return summarize(examples)
