"""Read Referenzliste and external Excel/CSV files, and build export tables."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from matching import normalize_text

HEADER_ALIASES = {
    "evo_id": ["evo id", "evoid", "evo"],
    "titel": ["titel", "title", "anrede"],
    "vorname": ["vorname", "first name", "firstname"],
    "nachname": ["nachname", "lastname", "last name", "familienname", "zuname"],
    "ort": ["ort", "stadt", "city", "wohnort"],
    "plz": ["plz", "postleitzahl", "postal code", "zip"],
    "hauptfach": ["hauptfach", "fach", "fachrichtung", "fachgebiet", "specialty"],
    "oek": ["ok nummer", "oek nummer", "oeknummer", "oknummer", "oek", "aerztenummer", "arztnummer"],
    "onekey": ["one key nummer", "onekey nummer", "one key", "onekey"],
}

ID_TOKENS = {"id", "nummer", "kunden", "customer", "nr", "kundennr"}

STATUS_LABELS = {
    "auto": "Automatisch",
    "likely": "Wahrscheinlich",
    "uncertain": "Unsicher",
    "unmatched": "Kein Treffer",
    "manual": "Manuell",
}


def read_table(filename: str, source: bytes) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        frame = pd.read_excel(io.BytesIO(source), dtype=str, keep_default_na=False)
    elif suffix in {".csv", ".txt"}:
        frame = _read_csv(source)
    else:
        raise ValueError("Nur Excel (.xlsx) oder CSV-Dateien werden gelesen.")
    frame.columns = [_clean_header(column) for column in frame.columns]
    if frame.empty and len(frame.columns) == 0:
        raise ValueError("Die Datei enthält keine Spalten.")
    return frame


def _read_csv(source: bytes) -> pd.DataFrame:
    text = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = source.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("Die CSV-Datei konnte nicht gelesen werden.")
    header = text.splitlines()[0] if text.strip() else ""
    separator = ";" if header.count(";") > header.count(",") else ","
    return pd.read_csv(io.StringIO(text), sep=separator, dtype=str, keep_default_na=False)


def _clean_header(column) -> str:
    text = str(column).strip()
    if text.lower().startswith("unnamed:"):
        return ""
    return text


def map_columns(columns: list[str]) -> tuple[dict[str, str], list[str]]:
    normalized = {column: normalize_text(column) for column in columns if column}
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for field, aliases in HEADER_ALIASES.items():
        alias_set = set(aliases)
        compact_aliases = {alias.replace(" ", "") for alias in aliases}
        for column, folded in normalized.items():
            if column in used:
                continue
            if folded in alias_set or folded.replace(" ", "") in compact_aliases:
                mapping[field] = column
                used.add(column)
                break
    customer_columns: list[str] = []
    for column, folded in normalized.items():
        if column in used or not folded:
            continue
        tokens = set(folded.split())
        if tokens & ID_TOKENS or "kunden" in folded or folded.endswith(" id"):
            customer_columns.append(column)
            used.add(column)
    return mapping, customer_columns


def _cell(row: pd.Series, column: str | None) -> str:
    if not column:
        return ""
    value = row.get(column, "")
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "nat"}:
        return ""
    return text


def parse_reference(frame: pd.DataFrame) -> tuple[list[dict], str, int]:
    mapping, _customer = map_columns(list(frame.columns))
    missing = [label for field, label in (("evo_id", "Evo-ID"), ("vorname", "Vorname"), ("nachname", "Nachname")) if field not in mapping]
    if missing:
        raise ValueError("Pflichtspalten fehlen: " + ", ".join(missing) + ".")

    seen: set[str] = set()
    doctors: list[dict] = []
    skipped: list[str] = []
    for index, row in frame.iterrows():
        evo_id = _cell(row, mapping["evo_id"])
        if not evo_id:
            skipped.append(f"Zeile {index + 2}: leere Evo-ID")
            continue
        key = evo_id.casefold()
        if key in seen:
            skipped.append(f"Zeile {index + 2}: doppelte Evo-ID {evo_id}")
            continue
        seen.add(key)
        doctors.append(
            {
                "evo_id": evo_id,
                "titel": _cell(row, mapping.get("titel")),
                "vorname": _cell(row, mapping["vorname"]),
                "nachname": _cell(row, mapping["nachname"]),
                "ort": _cell(row, mapping.get("ort")),
                "plz": _cell(row, mapping.get("plz")),
                "hauptfach": _cell(row, mapping.get("hauptfach")),
                "oek": _cell(row, mapping.get("oek")),
                "onekey": _cell(row, mapping.get("onekey")),
            }
        )
    recognized = ", ".join(mapping[field] for field in mapping)
    lines = [
        f"{len(doctors)} Einträge übernommen.",
        f"Spalten erkannt: {recognized}.",
    ]
    if skipped:
        preview = "; ".join(skipped[:8])
        extra = f" (+{len(skipped) - 8} weitere)" if len(skipped) > 8 else ""
        lines.append(f"{len(skipped)} Zeilen übersprungen: {preview}{extra}.")
    else:
        lines.append("Keine Zeilen übersprungen.")
    return doctors, "\n".join(lines), len(skipped)


def parse_external(frame: pd.DataFrame) -> tuple[list[dict], list[str], str]:
    mapping, customer_columns = map_columns(list(frame.columns))
    missing = [label for field, label in (("vorname", "Vorname"), ("nachname", "Nachname")) if field not in mapping]
    if missing:
        raise ValueError("Pflichtspalten fehlen: " + ", ".join(missing) + ".")

    rows: list[dict] = []
    for index, row in frame.iterrows():
        vorname = _cell(row, mapping["vorname"])
        nachname = _cell(row, mapping["nachname"])
        customer_ids = {column: _cell(row, column) for column in customer_columns}
        if not any((vorname, nachname, *customer_ids.values())):
            continue
        rows.append(
            {
                "row_number": int(index) + 2,
                "customer_ids": customer_ids,
                "titel": _cell(row, mapping.get("titel")),
                "vorname": vorname,
                "nachname": nachname,
                "plz": _cell(row, mapping.get("plz")),
                "ort": _cell(row, mapping.get("ort")),
                "hauptfach": _cell(row, mapping.get("hauptfach")),
                "oek": _cell(row, mapping.get("oek")),
                "onekey": _cell(row, mapping.get("onekey")),
            }
        )
    recognized = ", ".join(mapping[field] for field in mapping)
    id_text = ", ".join(customer_columns) if customer_columns else "keine"
    log = "\n".join(
        [
            f"{len(rows)} Zeilen gelesen.",
            f"Spalten erkannt: {recognized}.",
            f"Kunden-IDs: {id_text}.",
        ]
    )
    return rows, customer_columns, log


def export_frame(id_columns: list[str], rows: list[dict]) -> pd.DataFrame:
    records = []
    for row in rows:
        record = {column: row["customer_ids"].get(column, "") for column in id_columns}
        record.update(
            {
                "Titel": row["titel"],
                "Vorname": row["vorname"],
                "Nachname": row["nachname"],
                "PLZ": row["plz"],
                "Ort": row["ort"],
                "Hauptfach": row["hauptfach"],
                "ÖK-Nummer": row["oek"],
                "One-Key-Nummer": row["onekey"],
                "Status": STATUS_LABELS.get(row["match_status"], row["match_status"]),
                "Score": row["match_score"],
                "Methode": row["match_method"],
                "Hinweis": row["match_note"],
                "Evo-ID": row["match_evo_id"] or "",
                "Match Titel": row["match_titel"],
                "Match Vorname": row["match_vorname"],
                "Match Nachname": row["match_nachname"],
                "Match PLZ": row["match_plz"],
                "Match Ort": row["match_ort"],
                "Match Hauptfach": row["match_hauptfach"],
                "Match ÖK-Nummer": row["match_oek"],
                "Match One-Key-Nummer": row["match_onekey"],
            }
        )
        records.append(record)
    return pd.DataFrame.from_records(records)
