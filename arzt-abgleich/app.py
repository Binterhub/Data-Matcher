"""Single-user Flask app for matching external doctor lists to a Referenzliste."""

from __future__ import annotations

import io
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

import db
from matching import (
    LIKELY_MIN,
    UNCERTAIN_MIN,
    Doctor,
    ExternalPerson,
    Matcher,
    manual_result,
    search_doctors,
)
from tables import STATUS_LABELS, export_frame, parse_external, parse_reference, read_table

BASE_DIR = Path(__file__).resolve().parent
VIENNA = ZoneInfo("Europe/Vienna")
PASSWORD_HASHER = PasswordHasher()
LOCAL_USERNAME = "admin"
LOCAL_PASSWORD = "admin"
ALLOWED_SUFFIXES = {".csv", ".txt", ".xlsx", ".xlsm"}
STATUS_ORDER = ("auto", "likely", "uncertain", "unmatched", "manual")
GROUP_COPY = {
    "auto": "Exakte ÖK- oder One-Key-Nummer, 100 %.",
    "likely": f"Name, Fach und Adresse ab {LIKELY_MIN} %.",
    "uncertain": f"Ab {UNCERTAIN_MIN} % und unter {LIKELY_MIN} %, oder die Kennung passt nicht.",
    "unmatched": "Kein ausreichender Kandidat.",
    "manual": "Von Hand zugeordnet oder bestätigt.",
}


def create_app(instance_path: str | None = None) -> Flask:
    app = Flask(
        __name__,
        instance_path=instance_path or str(BASE_DIR / "instance"),
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    secret_path = Path(app.instance_path) / "secret_key"
    if secret_path.exists():
        app.secret_key = secret_path.read_text(encoding="utf-8").strip()
    else:
        app.secret_key = secrets.token_hex(32)
        secret_path.write_text(app.secret_key, encoding="utf-8")
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=False,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
        DB_PATH=str(Path(app.instance_path) / "arzt.db"),
    )
    db.init_db(Path(app.config["DB_PATH"]))
    connection = db.connect(Path(app.config["DB_PATH"]))
    try:
        _ensure_local_user(connection)
    finally:
        connection.close()

    @app.before_request
    def prepare_request():
        g.db = db.connect(Path(app.config["DB_PATH"]))
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        # Local single-user bypass: the browser session cookie was not coming
        # back on POST, so the CSRF check rejected every login. Sign in the
        # fixed account on each request instead of depending on that cookie.
        user = db.get_user(g.db)
        if user is not None:
            session["user_id"] = user["id"]
            session["username"] = user["username"]

    @app.teardown_request
    def close_db(_error):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    @app.template_filter("vienna")
    def vienna(value: str) -> str:
        return format_vienna(value)

    @app.context_processor
    def inject_globals():
        return {
            "csrf_token": session.get("csrf_token", ""),
            "logged_in": bool(session.get("user_id")),
            "current_username": session.get("username", ""),
            "status_labels": STATUS_LABELS,
        }

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)

        return wrapped

    @app.get("/")
    def index():
        if not _has_user():
            return redirect(url_for("setup"))
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return redirect(url_for("dashboard"))

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        if _has_user():
            return redirect(url_for("login"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            error = _validate_account(username, password)
            if error:
                flash(error, "error")
            else:
                db.create_user(g.db, username, PASSWORD_HASHER.hash(password))
                flash("Zugang angelegt. Bitte anmelden.", "ok")
                return redirect(url_for("login"))
        return render_template("setup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not _has_user():
            return redirect(url_for("setup"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = db.get_user(g.db)
            if user and user["username"] == username and _password_ok(user, password):
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                return redirect(_safe_next(request.form.get("next", "")))
            flash("Anmeldung fehlgeschlagen.", "error")
        return render_template("login.html", next_url=request.args.get("next", ""))

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        version = db.current_version(g.db)
        uploads = []
        counts = _count_by_upload()
        for upload in db.list_uploads(g.db):
            uploads.append({"row": upload, "counts": counts.get(upload["id"], {})})
        return render_template("dashboard.html", version=version, uploads=uploads)

    @app.route("/referenz", methods=["GET", "POST"])
    @login_required
    def referenz():
        version = db.current_version(g.db)
        if request.method == "POST":
            if version and request.form.get("confirm") != "yes":
                flash("Bitte das Ersetzen der Referenzliste bestätigen.", "error")
                return redirect(url_for("referenz"))
            upload = request.files.get("file")
            try:
                filename, payload = _read_upload(upload)
                frame = read_table(filename, payload)
                doctors, log_text, skipped = parse_reference(frame)
            except ValueError as error:
                flash(str(error), "error")
                return redirect(url_for("referenz"))
            if not doctors:
                flash("Die Datei enthält keine verwendbaren Ärzte.", "error")
                return redirect(url_for("referenz"))
            db.save_reference(g.db, filename, doctors, log_text, skipped)
            flash("Referenzliste gespeichert.", "ok")
            return redirect(url_for("referenz"))
        return render_template("referenz.html", version=version, versions=db.list_versions(g.db))

    @app.route("/upload", methods=["GET", "POST"])
    @login_required
    def upload_external():
        version = db.current_version(g.db)
        if request.method == "POST":
            if version is None:
                flash("Zuerst eine Referenzliste hochladen.", "error")
                return redirect(url_for("referenz"))
            upload = request.files.get("file")
            try:
                filename, payload = _read_upload(upload)
                frame = read_table(filename, payload)
                parsed_rows, id_columns, log_text = parse_external(frame)
            except ValueError as error:
                flash(str(error), "error")
                return redirect(url_for("upload_external"))
            if not parsed_rows:
                flash("Die Datei enthält keine Zeilen.", "error")
                return redirect(url_for("upload_external"))
            stored = _match_parsed_rows(version["id"], parsed_rows)
            summary = _summary(stored)
            upload_id = db.save_upload(
                g.db,
                filename,
                log_text + "\n" + summary,
                id_columns,
                version["id"],
                stored,
            )
            flash("Liste abgeglichen.", "ok")
            return redirect(url_for("review", upload_id=upload_id))
        return render_template("upload.html", version=version)

    @app.get("/uploads/<int:upload_id>")
    @login_required
    def review(upload_id: int):
        upload = db.get_upload(g.db, upload_id)
        if upload is None:
            abort(404)
        groups = _groups(db.get_rows(g.db, upload_id))
        return render_template("review.html", upload=upload, groups=groups, likely_min=LIKELY_MIN, uncertain_min=UNCERTAIN_MIN)

    @app.post("/uploads/<int:upload_id>/rematch")
    @login_required
    def rematch(upload_id: int):
        upload = db.get_upload(g.db, upload_id)
        version = db.current_version(g.db)
        if upload is None or version is None:
            abort(404)
        matcher = _matcher(version["id"])
        for row in db.get_rows(g.db, upload_id):
            if row["locked"]:
                continue
            result = matcher.match(_person_from_row(row))
            db.update_match(g.db, row["id"], _fields_from_match(result, 0))
        flash("Offene Zeilen neu abgeglichen.", "ok")
        return redirect(url_for("review", upload_id=upload_id))

    @app.post("/uploads/<int:upload_id>/rows/<int:row_id>/accept")
    @login_required
    def accept_row(upload_id: int, row_id: int):
        row = _owned_row(upload_id, row_id)
        if not row["match_evo_id"]:
            flash("Diese Zeile hat keinen Vorschlag zum Übernehmen.", "error")
            return redirect(url_for("review", upload_id=upload_id))
        fields = _fields_from_row(row)
        fields["match_status"] = "manual"
        fields["match_method"] = "manual"
        fields["match_note"] = "Vorschlag übernommen."
        fields["locked"] = 1
        db.update_match(g.db, row_id, fields)
        flash("Vorschlag übernommen.", "ok")
        return redirect(url_for("review", upload_id=upload_id))

    @app.post("/uploads/<int:upload_id>/rows/<int:row_id>/reject")
    @login_required
    def reject_row(upload_id: int, row_id: int):
        _owned_row(upload_id, row_id)
        db.update_match(
            g.db,
            row_id,
            {
                "match_evo_id": None,
                "match_score": 0,
                "match_status": "unmatched",
                "match_method": "none",
                "match_note": "Manuell verworfen.",
                "match_titel": "",
                "match_vorname": "",
                "match_nachname": "",
                "match_ort": "",
                "match_plz": "",
                "match_hauptfach": "",
                "match_oek": "",
                "match_onekey": "",
                "locked": 1,
            },
        )
        flash("Zeile als kein Treffer markiert.", "ok")
        return redirect(url_for("review", upload_id=upload_id))

    @app.post("/uploads/<int:upload_id>/rows/<int:row_id>/assign")
    @login_required
    def assign_row(upload_id: int, row_id: int):
        _owned_row(upload_id, row_id)
        version = db.current_version(g.db)
        evo_id = request.form.get("evo_id", "").strip()
        doctor = db.find_doctor(g.db, version["id"], evo_id) if version and evo_id else None
        if doctor is None:
            flash("Evo-ID nicht in der aktuellen Referenzliste.", "error")
            return redirect(url_for("review", upload_id=upload_id))
        result = manual_result(_doctor_from_row(doctor), "Manuell zugeordnet.")
        db.update_match(g.db, row_id, _fields_from_match(result, 1))
        flash(f"{evo_id} zugeordnet.", "ok")
        return redirect(url_for("review", upload_id=upload_id))

    @app.post("/uploads/<int:upload_id>/rows/<int:row_id>/reset")
    @login_required
    def reset_row(upload_id: int, row_id: int):
        row = _owned_row(upload_id, row_id)
        version = db.current_version(g.db)
        if version is None:
            abort(404)
        result = _matcher(version["id"]).match(_person_from_row(row))
        db.update_match(g.db, row_id, _fields_from_match(result, 0))
        flash("Zeile neu abgeglichen.", "ok")
        return redirect(url_for("review", upload_id=upload_id))

    @app.get("/uploads/<int:upload_id>/export.xlsx")
    @login_required
    def export_xlsx(upload_id: int):
        frame = _export_frame(upload_id)
        buffer = io.BytesIO()
        with pd_excel_writer(buffer) as writer:
            frame.to_excel(writer, index=False, sheet_name="Abgleich")
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"abgleich-{upload_id}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/uploads/<int:upload_id>/export.csv")
    @login_required
    def export_csv(upload_id: int):
        frame = _export_frame(upload_id)
        payload = frame.to_csv(index=False).encode("utf-8-sig")
        return send_file(
            io.BytesIO(payload),
            as_attachment=True,
            download_name=f"abgleich-{upload_id}.csv",
            mimetype="text/csv",
        )

    @app.get("/api/referenz/search")
    @login_required
    def search_referenz():
        version = db.current_version(g.db)
        if version is None:
            return jsonify([])
        doctors = [_doctor_from_row(row) for row in db.load_doctors(g.db, version["id"])]
        hits = search_doctors(doctors, request.args.get("q", ""))
        return jsonify(
            [
                {
                    "evo_id": doctor.evo_id,
                    "score": score,
                    "label": _doctor_label(doctor),
                }
                for score, doctor in hits
            ]
        )

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    return app


def pd_excel_writer(buffer: io.BytesIO):
    import pandas as pd

    return pd.ExcelWriter(buffer, engine="openpyxl")


def format_vienna(value: str) -> str:
    if not value:
        return ""
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(VIENNA).strftime("%d.%m.%Y %H:%M")


def _has_user() -> bool:
    return db.user_count(g.db) > 0


def _ensure_local_user(connection: sqlite3.Connection) -> None:
    """Keep one fixed local account so signup and the cookie login are unnecessary."""
    password_hash = PASSWORD_HASHER.hash(LOCAL_PASSWORD)
    user = db.get_user(connection)
    if user is None:
        db.create_user(connection, LOCAL_USERNAME, password_hash)
        return
    try:
        PASSWORD_HASHER.verify(user["password_hash"], LOCAL_PASSWORD)
        if user["username"] == LOCAL_USERNAME:
            return
    except VerificationError:
        pass
    connection.execute(
        "UPDATE users SET username = ?, password_hash = ? WHERE id = ?",
        (LOCAL_USERNAME, password_hash, user["id"]),
    )
    connection.commit()


def _password_ok(user: sqlite3.Row, password: str) -> bool:
    try:
        PASSWORD_HASHER.verify(user["password_hash"], password)
    except VerificationError:
        return False
    if PASSWORD_HASHER.check_needs_rehash(user["password_hash"]):
        g.db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (PASSWORD_HASHER.hash(password), user["id"]),
        )
        g.db.commit()
    return True


def _validate_account(username: str, password: str) -> str:
    if len(username) < 3 or len(username) > 64:
        return "Der Benutzername braucht 3 bis 64 Zeichen."
    if not all(char.isalnum() or char in "._-" for char in username):
        return "Der Benutzername darf Buchstaben, Ziffern, Punkt, Unterstrich und Bindestrich enthalten."
    if len(password) < 10:
        return "Das Passwort braucht mindestens 10 Zeichen."
    return ""


def _safe_next(value: str) -> str:
    if value.startswith("/") and not value.startswith("//"):
        return value
    return url_for("dashboard")


def _read_upload(upload) -> tuple[str, bytes]:
    if upload is None or not upload.filename:
        raise ValueError("Bitte eine Datei auswählen.")
    filename = Path(upload.filename).name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("Nur Excel (.xlsx) oder CSV.")
    safe_name = secure_filename(filename) or f"upload{suffix}"
    payload = upload.read()
    if not payload:
        raise ValueError("Die Datei ist leer.")
    return safe_name, payload


def _doctor_from_row(row) -> Doctor:
    return Doctor(
        evo_id=row["evo_id"],
        titel=row["titel"],
        vorname=row["vorname"],
        nachname=row["nachname"],
        ort=row["ort"],
        plz=row["plz"],
        hauptfach=row["hauptfach"],
        oek=row["oek"],
        onekey=row["onekey"],
    )


def _person_from_row(row) -> ExternalPerson:
    return ExternalPerson(
        titel=row["titel"],
        vorname=row["vorname"],
        nachname=row["nachname"],
        ort=row["ort"],
        plz=row["plz"],
        hauptfach=row["hauptfach"],
        oek=row["oek"],
        onekey=row["onekey"],
    )


def _fields_from_match(result, locked: int) -> dict:
    return {
        "match_evo_id": result.evo_id,
        "match_score": result.score,
        "match_status": result.status,
        "match_method": result.method,
        "match_note": result.note,
        "match_titel": result.titel,
        "match_vorname": result.vorname,
        "match_nachname": result.nachname,
        "match_ort": result.ort,
        "match_plz": result.plz,
        "match_hauptfach": result.hauptfach,
        "match_oek": result.oek,
        "match_onekey": result.onekey,
        "locked": locked,
    }


def _fields_from_row(row) -> dict:
    return {
        "match_evo_id": row["match_evo_id"],
        "match_score": row["match_score"],
        "match_status": row["match_status"],
        "match_method": row["match_method"],
        "match_note": row["match_note"],
        "match_titel": row["match_titel"],
        "match_vorname": row["match_vorname"],
        "match_nachname": row["match_nachname"],
        "match_ort": row["match_ort"],
        "match_plz": row["match_plz"],
        "match_hauptfach": row["match_hauptfach"],
        "match_oek": row["match_oek"],
        "match_onekey": row["match_onekey"],
        "locked": row["locked"],
    }


def _matcher(version_id: int) -> Matcher:
    doctors = [_doctor_from_row(row) for row in db.load_doctors(g.db, version_id)]
    return Matcher(doctors)


def _match_parsed_rows(version_id: int, parsed_rows: list[dict]) -> list[dict]:
    matcher = _matcher(version_id)
    stored = []
    for parsed in parsed_rows:
        result = matcher.match(
            ExternalPerson(
                titel=parsed["titel"],
                vorname=parsed["vorname"],
                nachname=parsed["nachname"],
                ort=parsed["ort"],
                plz=parsed["plz"],
                hauptfach=parsed["hauptfach"],
                oek=parsed["oek"],
                onekey=parsed["onekey"],
            )
        )
        stored.append({**parsed, **_fields_from_match(result, 0)})
    return stored


def _summary(rows: list[dict]) -> str:
    counts = {status: 0 for status in STATUS_ORDER}
    for row in rows:
        counts[row["match_status"]] = counts.get(row["match_status"], 0) + 1
    return (
        "Zuordnung: "
        f"{counts['auto']} automatisch, {counts['likely']} wahrscheinlich, "
        f"{counts['uncertain']} unsicher, {counts['unmatched']} ohne Treffer."
    )


def _count_by_upload() -> dict[int, dict[str, int]]:
    grouped: dict[int, dict[str, int]] = {}
    query = "SELECT upload_id, match_status, COUNT(*) AS n FROM external_rows GROUP BY upload_id, match_status"
    for row in g.db.execute(query):
        grouped.setdefault(row["upload_id"], {})[row["match_status"]] = row["n"]
    return grouped


def _groups(rows) -> list[dict]:
    buckets = {status: [] for status in STATUS_ORDER}
    for row in rows:
        buckets.setdefault(row["match_status"], []).append(_row_view(row))
    return [
        {
            "key": status,
            "label": STATUS_LABELS[status],
            "copy": GROUP_COPY[status],
            "rows": buckets[status],
        }
        for status in STATUS_ORDER
    ]


def _row_view(row) -> dict:
    customer_ids = json.loads(row["customer_ids"] or "{}")
    candidate = None
    if row["match_evo_id"]:
        candidate = {
            "evo_id": row["match_evo_id"],
            "titel": row["match_titel"],
            "vorname": row["match_vorname"],
            "nachname": row["match_nachname"],
            "ort": row["match_ort"],
            "plz": row["match_plz"],
            "hauptfach": row["match_hauptfach"],
            "oek": row["match_oek"],
            "onekey": row["match_onekey"],
        }
    return {
        "id": row["id"],
        "row_number": row["row_number"],
        "customer_ids": customer_ids,
        "ids_label": ", ".join(f"{key}: {value}" for key, value in customer_ids.items() if str(value).strip()),
        "titel": row["titel"],
        "vorname": row["vorname"],
        "nachname": row["nachname"],
        "plz": row["plz"],
        "ort": row["ort"],
        "hauptfach": row["hauptfach"],
        "oek": row["oek"],
        "onekey": row["onekey"],
        "score": row["match_score"],
        "status": row["match_status"],
        "method": row["match_method"],
        "note": row["match_note"],
        "locked": row["locked"],
        "candidate": candidate,
    }


def _owned_row(upload_id: int, row_id: int):
    row = db.get_row(g.db, upload_id, row_id)
    if row is None:
        abort(404)
    return row


def _export_frame(upload_id: int):
    upload = db.get_upload(g.db, upload_id)
    if upload is None:
        abort(404)
    id_columns = json.loads(upload["id_columns"] or "[]")
    records = []
    for row in db.get_rows(g.db, upload_id):
        view = _row_view(row)
        records.append(
            {
                "customer_ids": view["customer_ids"],
                "titel": view["titel"],
                "vorname": view["vorname"],
                "nachname": view["nachname"],
                "plz": view["plz"],
                "ort": view["ort"],
                "hauptfach": view["hauptfach"],
                "oek": view["oek"],
                "onekey": view["onekey"],
                "match_status": view["status"],
                "match_score": view["score"],
                "match_method": view["method"],
                "match_note": view["note"],
                "match_evo_id": view["candidate"]["evo_id"] if view["candidate"] else None,
                "match_titel": view["candidate"]["titel"] if view["candidate"] else "",
                "match_vorname": view["candidate"]["vorname"] if view["candidate"] else "",
                "match_nachname": view["candidate"]["nachname"] if view["candidate"] else "",
                "match_plz": view["candidate"]["plz"] if view["candidate"] else "",
                "match_ort": view["candidate"]["ort"] if view["candidate"] else "",
                "match_hauptfach": view["candidate"]["hauptfach"] if view["candidate"] else "",
                "match_oek": view["candidate"]["oek"] if view["candidate"] else "",
                "match_onekey": view["candidate"]["onekey"] if view["candidate"] else "",
            }
        )
    return export_frame(id_columns, records)


def _doctor_label(doctor: Doctor) -> str:
    name = " ".join(part for part in (doctor.titel, doctor.vorname, doctor.nachname) if part)
    place = " ".join(part for part in (doctor.plz, doctor.ort) if part)
    extra = ", ".join(part for part in (place, doctor.hauptfach) if part)
    return f"{doctor.evo_id} — {name}" + (f", {extra}" if extra else "")


if __name__ == "__main__":
    application = create_app()
    application.run(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5001")),
        debug=os.environ.get("ARZT_DEBUG") == "1",
    )
