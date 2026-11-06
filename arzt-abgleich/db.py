"""SQLite storage for the single user, Referenzliste versions, and match runs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reference_versions (
    id INTEGER PRIMARY KEY,
    uploaded_at TEXT NOT NULL,
    filename TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    skipped INTEGER NOT NULL,
    log_text TEXT NOT NULL,
    is_current INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS reference_doctors (
    id INTEGER PRIMARY KEY,
    version_id INTEGER NOT NULL REFERENCES reference_versions(id),
    evo_id TEXT NOT NULL,
    titel TEXT NOT NULL,
    vorname TEXT NOT NULL,
    nachname TEXT NOT NULL,
    ort TEXT NOT NULL,
    plz TEXT NOT NULL,
    hauptfach TEXT NOT NULL,
    oek TEXT NOT NULL,
    onekey TEXT NOT NULL,
    wahlart TEXT NOT NULL DEFAULT '',
    UNIQUE(version_id, evo_id)
);

CREATE TABLE IF NOT EXISTS external_uploads (
    id INTEGER PRIMARY KEY,
    uploaded_at TEXT NOT NULL,
    filename TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    log_text TEXT NOT NULL,
    id_columns TEXT NOT NULL,
    reference_version_id INTEGER
);

CREATE TABLE IF NOT EXISTS external_rows (
    id INTEGER PRIMARY KEY,
    upload_id INTEGER NOT NULL REFERENCES external_uploads(id),
    row_number INTEGER NOT NULL,
    customer_ids TEXT NOT NULL,
    titel TEXT NOT NULL,
    vorname TEXT NOT NULL,
    nachname TEXT NOT NULL,
    plz TEXT NOT NULL,
    ort TEXT NOT NULL,
    hauptfach TEXT NOT NULL,
    oek TEXT NOT NULL,
    onekey TEXT NOT NULL,
    wahlart TEXT NOT NULL DEFAULT '',
    match_evo_id TEXT,
    match_score INTEGER NOT NULL,
    match_status TEXT NOT NULL,
    match_method TEXT NOT NULL,
    match_note TEXT NOT NULL,
    match_titel TEXT NOT NULL,
    match_vorname TEXT NOT NULL,
    match_nachname TEXT NOT NULL,
    match_ort TEXT NOT NULL,
    match_plz TEXT NOT NULL,
    match_hauptfach TEXT NOT NULL,
    match_oek TEXT NOT NULL,
    match_onekey TEXT NOT NULL,
    match_wahlart TEXT NOT NULL DEFAULT '',
    locked INTEGER NOT NULL DEFAULT 0
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as connection:
        connection.executescript(SCHEMA)
        _ensure_column(connection, "reference_doctors", "wahlart")
        _ensure_column(connection, "external_rows", "wahlart")
        _ensure_column(connection, "external_rows", "match_wahlart")
        connection.commit()


def _ensure_column(connection: sqlite3.Connection, table: str, column: str) -> None:
    present = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in present:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")


def user_count(connection: sqlite3.Connection) -> int:
    return int(connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])


def get_user(connection: sqlite3.Connection) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM users ORDER BY id LIMIT 1").fetchone()


def create_user(connection: sqlite3.Connection, username: str, password_hash: str) -> None:
    if user_count(connection):
        raise RuntimeError("Es gibt bereits einen Benutzer.")
    connection.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
        (username, password_hash, utcnow()),
    )
    connection.commit()


def list_versions(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM reference_versions ORDER BY uploaded_at DESC, id DESC"
    ).fetchall()


def current_version(connection: sqlite3.Connection) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM reference_versions WHERE is_current = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()


def save_reference(connection: sqlite3.Connection, filename: str, doctors: list[dict], log_text: str, skipped: int) -> int:
    connection.execute("UPDATE reference_versions SET is_current = 0 WHERE is_current = 1")
    cursor = connection.execute(
        """INSERT INTO reference_versions
           (uploaded_at, filename, row_count, skipped, log_text, is_current)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (utcnow(), filename, len(doctors), skipped, log_text),
    )
    version_id = int(cursor.lastrowid)
    connection.executemany(
        """INSERT INTO reference_doctors
           (version_id, evo_id, titel, vorname, nachname, ort, plz, hauptfach, oek, onekey, wahlart)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                version_id,
                doctor["evo_id"],
                doctor["titel"],
                doctor["vorname"],
                doctor["nachname"],
                doctor["ort"],
                doctor["plz"],
                doctor["hauptfach"],
                doctor["oek"],
                doctor["onekey"],
                doctor["wahlart"],
            )
            for doctor in doctors
        ],
    )
    connection.commit()
    return version_id


def load_doctors(connection: sqlite3.Connection, version_id: int) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM reference_doctors WHERE version_id = ? ORDER BY nachname, vorname, evo_id",
        (version_id,),
    ).fetchall()


def save_upload(
    connection: sqlite3.Connection,
    filename: str,
    log_text: str,
    id_columns: list[str],
    reference_version_id: int | None,
    rows: list[dict],
) -> int:
    cursor = connection.execute(
        """INSERT INTO external_uploads
           (uploaded_at, filename, row_count, log_text, id_columns, reference_version_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (utcnow(), filename, len(rows), log_text, json.dumps(id_columns, ensure_ascii=False), reference_version_id),
    )
    upload_id = int(cursor.lastrowid)
    connection.executemany(
        """INSERT INTO external_rows (
               upload_id, row_number, customer_ids, titel, vorname, nachname, plz, ort,
               hauptfach, oek, onekey, wahlart, match_evo_id, match_score, match_status, match_method,
               match_note, match_titel, match_vorname, match_nachname, match_ort, match_plz,
               match_hauptfach, match_oek, match_onekey, match_wahlart, locked
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                upload_id,
                row["row_number"],
                json.dumps(row["customer_ids"], ensure_ascii=False),
                row["titel"],
                row["vorname"],
                row["nachname"],
                row["plz"],
                row["ort"],
                row["hauptfach"],
                row["oek"],
                row["onekey"],
                row["wahlart"],
                row["match_evo_id"],
                row["match_score"],
                row["match_status"],
                row["match_method"],
                row["match_note"],
                row["match_titel"],
                row["match_vorname"],
                row["match_nachname"],
                row["match_ort"],
                row["match_plz"],
                row["match_hauptfach"],
                row["match_oek"],
                row["match_onekey"],
                row["match_wahlart"],
                row["locked"],
            )
            for row in rows
        ],
    )
    connection.commit()
    return upload_id


def list_uploads(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM external_uploads ORDER BY uploaded_at DESC, id DESC"
    ).fetchall()


def get_upload(connection: sqlite3.Connection, upload_id: int) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM external_uploads WHERE id = ?", (upload_id,)).fetchone()


def get_rows(connection: sqlite3.Connection, upload_id: int) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM external_rows WHERE upload_id = ? ORDER BY row_number, id",
        (upload_id,),
    ).fetchall()


def get_row(connection: sqlite3.Connection, upload_id: int, row_id: int) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM external_rows WHERE upload_id = ? AND id = ?",
        (upload_id, row_id),
    ).fetchone()


def update_match(connection: sqlite3.Connection, row_id: int, fields: dict) -> None:
    connection.execute(
        """UPDATE external_rows SET
               match_evo_id = ?, match_score = ?, match_status = ?, match_method = ?,
               match_note = ?, match_titel = ?, match_vorname = ?, match_nachname = ?,
               match_ort = ?, match_plz = ?, match_hauptfach = ?, match_oek = ?,
               match_onekey = ?, match_wahlart = ?, locked = ?
           WHERE id = ?""",
        (
            fields["match_evo_id"],
            fields["match_score"],
            fields["match_status"],
            fields["match_method"],
            fields["match_note"],
            fields["match_titel"],
            fields["match_vorname"],
            fields["match_nachname"],
            fields["match_ort"],
            fields["match_plz"],
            fields["match_hauptfach"],
            fields["match_oek"],
            fields["match_onekey"],
            fields["match_wahlart"],
            fields["locked"],
            row_id,
        ),
    )
    connection.commit()


def wahlart_summary(connection: sqlite3.Connection, version_id: int) -> dict[str, int]:
    counts = {"ja": 0, "nein": 0}
    rows = connection.execute(
        "SELECT wahlart, COUNT(*) AS n FROM reference_doctors WHERE version_id = ? GROUP BY wahlart",
        (version_id,),
    )
    for row in rows:
        if row["wahlart"] in counts:
            counts[row["wahlart"]] = row["n"]
    return counts


def find_doctor(connection: sqlite3.Connection, version_id: int, evo_id: str) -> sqlite3.Row | None:
    return connection.execute(
        """SELECT * FROM reference_doctors
           WHERE version_id = ? AND evo_id = ? COLLATE NOCASE""",
        (version_id, evo_id.strip()),
    ).fetchone()
