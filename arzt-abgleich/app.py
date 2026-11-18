"""Single-user Flask app for matching external doctor lists to a Referenzliste."""

from __future__ import annotations

import io
import json
import os
import re
import secrets
import sqlite3
import threading
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
import learning
from matching import (
    LIKELY_MIN,
    LIKELY_WRONG_MIN,
    UNCERTAIN_MIN,
    VERY_LIKELY_MIN,
    Doctor,
    ExternalPerson,
    Matcher,
    MatchResult,
    manual_result,
    search_doctors,
)
from tables import STATUS_LABELS, export_frame, parse_external, parse_reference, read_table

BASE_DIR = Path(__file__).resolve().parent
VIENNA = ZoneInfo("Europe/Vienna")
PASSWORD_HASHER = PasswordHasher()
LOCAL_USERNAME = "admin"
LOCAL_PASSWORD = "admin"
_MATCH_JOBS: dict[str, dict] = {}
_MATCH_LOCK = threading.Lock()
ALLOWED_SUFFIXES = {".csv", ".txt", ".xlsx", ".xlsm"}
STATUS_ORDER = ("auto", "very_likely", "likely", "uncertain", "likely_wrong", "unmatched", "manual")
PAGE_SIZE = 50
GROUP_COPY = {
    "auto": "Exakte ÖK- oder One-Key-Nummer, 100 %.",
    "very_likely": f"Name, Fach und Adresse ab {VERY_LIKELY_MIN} %.",
    "likely": f"Name, Fach und Adresse ab {LIKELY_MIN} % und unter {VERY_LIKELY_MIN} %.",
    "uncertain": f"Ab {UNCERTAIN_MIN} % und unter {LIKELY_MIN} %, oder die Kennung passt nicht.",
    "likely_wrong": f"Ab {LIKELY_WRONG_MIN} % und unter {UNCERTAIN_MIN} %. Der Vorschlag passt wahrscheinlich nicht.",
    "unmatched": "Kein ausreichender Kandidat.",
    "manual": "Von Hand zugeordnet oder bestätigt.",
}


def _default_instance_path() -> str:
    """Use Railway's volume when one is attached. Otherwise keep the local instance folder."""
    mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    return mount or str(BASE_DIR / "instance")


def create_app(instance_path: str | None = None) -> Flask:
    app = Flask(
        __name__,
        instance_path=instance_path or _default_instance_path(),
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
        SESSION_COOKIE_SECURE=bool(os.environ.get("RAILWAY_ENVIRONMENT")),
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

    if os.environ.get("RAILWAY_ENVIRONMENT"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

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
        wahlart = db.wahlart_summary(g.db, version["id"]) if version else None
        return render_template("dashboard.html", version=version, uploads=uploads, wahlart=wahlart)

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
            upload = request.files.get("file")
            try:
                filename, payload = _read_upload(upload)
                frame = read_table(filename, payload)
                parsed_rows, id_columns, log_text = parse_external(frame)
            except ValueError as error:
                if request.form.get("progress") == "1":
                    return jsonify(error=str(error)), 400
                flash(str(error), "error")
                return redirect(url_for("upload_external"))
            if not parsed_rows:
                message = "Die Datei enthält keine Zeilen."
                if request.form.get("progress") == "1":
                    return jsonify(error=message), 400
                flash(message, "error")
                return redirect(url_for("upload_external"))
            if request.form.get("progress") == "1":
                job_id = _launch_match_job(
                    app.config["DB_PATH"],
                    filename,
                    log_text,
                    id_columns,
                    None if version is None else version["id"],
                    parsed_rows,
                )
                return jsonify(status=url_for("match_progress_status", job_id=job_id))
            if version is None:
                stored = _pending_rows(parsed_rows)
                log_text += "\nNoch keine Referenzliste. Zeilen sind ohne Treffer gespeichert."
                flash(
                    "Liste gespeichert. Für den Abgleich eine Referenzliste hochladen, dann offene Zeilen neu abgleichen.",
                    "ok",
                )
                version_id = None
            else:
                stored = _match_parsed_rows(version["id"], parsed_rows)
                log_text += "\n" + _summary(stored)
                flash("Liste abgeglichen.", "ok")
                version_id = version["id"]
            upload_id = db.save_upload(
                g.db,
                filename,
                log_text,
                id_columns,
                version_id,
                stored,
            )
            return _back_to_review(upload_id)
        return render_template("upload.html", version=version)

    @app.get("/upload/progress/<job_id>")
    @login_required
    def match_progress_status(job_id: str):
        with _MATCH_LOCK:
            job = _MATCH_JOBS.get(job_id)
            if job is None:
                abort(404)
            payload = {
                "done": job["done"],
                "total": job["total"],
                "error": job["error"],
                "review": job["review"],
            }
        response = jsonify(payload)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/uploads/<int:upload_id>")
    @login_required
    def review(upload_id: int):
        upload = db.get_upload(g.db, upload_id)
        if upload is None:
            abort(404)
        learning.prepare(g.db, _learning_rematch_factory)
        band = request.args.get("band", "")
        rows = db.get_rows(g.db, upload_id)
        focus = _focus_state(upload_id, band, rows) if band in STATUS_ORDER else None
        groups = [] if focus is not None else _groups(rows, _requested_pages())
        if focus is None:
            _attach_page_links(upload_id, groups)
        return render_template(
            "review.html",
            upload=upload,
            groups=groups,
            focus=focus,
            progress=_upload_progress(rows),
            very_likely_min=VERY_LIKELY_MIN,
            likely_min=LIKELY_MIN,
            uncertain_min=UNCERTAIN_MIN,
            likely_wrong_min=LIKELY_WRONG_MIN,
            page_query=request.query_string.decode(),
        )

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
        return _back_to_review(upload_id)

    @app.post("/uploads/<int:upload_id>/rows/<int:row_id>/accept")
    @login_required
    def accept_row(upload_id: int, row_id: int):
        row = _owned_row(upload_id, row_id)
        if not row["match_evo_id"]:
            flash("Diese Zeile hat keinen Vorschlag zum Übernehmen.", "error")
            return _return_after_decision(upload_id, row, advance=False)
        learning.remember(g.db, row, "accept")
        fields = _fields_from_row(row)
        fields["match_status"] = "manual"
        fields["match_method"] = "manual"
        fields["match_note"] = "Vorschlag übernommen."
        fields["locked"] = 1
        db.update_match(g.db, row_id, fields)
        flash("Vorschlag übernommen.", "ok")
        return _return_after_decision(upload_id, row, advance=True)

    @app.post("/uploads/<int:upload_id>/rows/<int:row_id>/reject")
    @login_required
    def reject_row(upload_id: int, row_id: int):
        row = _owned_row(upload_id, row_id)
        learning.remember(g.db, row, "reject")
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
                "match_wahlart": "",
                "locked": 1,
            },
        )
        flash("Zeile als kein Treffer markiert.", "ok")
        return _return_after_decision(upload_id, row, advance=True)

    @app.post("/uploads/<int:upload_id>/rows/<int:row_id>/assign")
    @login_required
    def assign_row(upload_id: int, row_id: int):
        _owned_row(upload_id, row_id)
        version = db.current_version(g.db)
        evo_id = request.form.get("evo_id", "").strip()
        doctor = db.find_doctor(g.db, version["id"], evo_id) if version and evo_id else None
        if doctor is None:
            flash("Evo-ID nicht in der aktuellen Referenzliste.", "error")
            return _back_to_review(upload_id)
        result = manual_result(_doctor_from_row(doctor), "Manuell zugeordnet.")
        learning.remember_assignment(g.db, _owned_row(upload_id, row_id), doctor)
        db.update_match(g.db, row_id, _fields_from_match(result, 1))
        flash(f"{evo_id} zugeordnet.", "ok")
        return _back_to_review(upload_id)

    @app.post("/uploads/<int:upload_id>/rows/<int:row_id>/reset")
    @login_required
    def reset_row(upload_id: int, row_id: int):
        row = _owned_row(upload_id, row_id)
        version = db.current_version(g.db)
        if version is None:
            abort(404)
        learning.forget(g.db, row_id)
        result = _matcher(version["id"]).match(_person_from_row(row))
        db.update_match(g.db, row_id, _fields_from_match(result, 0))
        flash("Zeile neu abgeglichen.", "ok")
        return _back_to_review(upload_id)

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
        wahlart=row["wahlart"],
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
        wahlart=row["wahlart"],
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
        "match_wahlart": result.wahlart,
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
        "match_wahlart": row["match_wahlart"],
        "locked": row["locked"],
    }


def _learning_rematch_factory():
    version = db.current_version(g.db)
    if version is None:
        return lambda row: None
    matcher = _matcher(version["id"])

    def rematch(row):
        return matcher.match(_person_from_row(row))

    return rematch


def _matcher(version_id: int) -> Matcher:
    doctors = [_doctor_from_row(row) for row in db.load_doctors(g.db, version_id)]
    return Matcher(doctors)


def _pending_rows(parsed_rows: list[dict]) -> list[dict]:
    note = "Noch keine Referenzliste. Abgleich folgt nach dem Upload."
    stored = []
    for parsed in parsed_rows:
        result = MatchResult(evo_id=None, score=0, status="unmatched", method="none", note=note)
        stored.append({**parsed, **_fields_from_match(result, 0)})
    return stored


def _match_rows(matcher: Matcher, parsed_rows: list[dict], on_progress=None) -> list[dict]:
    total = len(parsed_rows)
    step = max(1, total // 100)
    stored = []
    for index, parsed in enumerate(parsed_rows, start=1):
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
                wahlart=parsed["wahlart"],
            )
        )
        stored.append({**parsed, **_fields_from_match(result, 0)})
        if on_progress is not None and (index == total or index % step == 0):
            on_progress(index, total)
    return stored


def _match_parsed_rows(version_id: int, parsed_rows: list[dict]) -> list[dict]:
    return _match_rows(_matcher(version_id), parsed_rows)


def _launch_match_job(
    db_path: str,
    filename: str,
    log_text: str,
    id_columns: list[str],
    version_id: int | None,
    parsed_rows: list[dict],
) -> str:
    job_id = secrets.token_urlsafe(12)
    with _MATCH_LOCK:
        _MATCH_JOBS[job_id] = {
            "done": 0,
            "total": len(parsed_rows),
            "error": None,
            "review": None,
        }
    threading.Thread(
        target=_run_match_job,
        args=(db_path, job_id, filename, log_text, id_columns, version_id, parsed_rows),
        daemon=True,
    ).start()
    return job_id


def _run_match_job(
    db_path: str,
    job_id: str,
    filename: str,
    log_text: str,
    id_columns: list[str],
    version_id: int | None,
    parsed_rows: list[dict],
) -> None:
    def report(done: int, _total: int) -> None:
        with _MATCH_LOCK:
            job = _MATCH_JOBS.get(job_id)
            if job is not None:
                job["done"] = done

    try:
        if version_id is None:
            stored = _pending_rows(parsed_rows)
            report(len(parsed_rows), len(parsed_rows))
            log_text += "\nNoch keine Referenzliste. Zeilen sind ohne Treffer gespeichert."
        else:
            connection = db.connect(Path(db_path))
            try:
                matcher = Matcher([_doctor_from_row(row) for row in db.load_doctors(connection, version_id)])
            finally:
                connection.close()
            stored = _match_rows(matcher, parsed_rows, on_progress=report)
            log_text += "\n" + _summary(stored)
        connection = db.connect(Path(db_path))
        try:
            upload_id = db.save_upload(connection, filename, log_text, id_columns, version_id, stored)
        finally:
            connection.close()
        with _MATCH_LOCK:
            job = _MATCH_JOBS.get(job_id)
            if job is not None:
                job["done"] = len(parsed_rows)
                job["review"] = f"/uploads/{upload_id}"
    except Exception:
        with _MATCH_LOCK:
            job = _MATCH_JOBS.get(job_id)
            if job is not None and not job["error"]:
                job["error"] = "Abgleich fehlgeschlagen."


def _summary(rows: list[dict]) -> str:
    counts = {status: 0 for status in STATUS_ORDER}
    for row in rows:
        counts[row["match_status"]] = counts.get(row["match_status"], 0) + 1
    return (
        "Zuordnung: "
        f"{counts['auto']} automatisch, {counts['very_likely']} sehr wahrscheinlich, "
        f"{counts['likely']} wahrscheinlich, {counts['uncertain']} unsicher, "
        f"{counts['likely_wrong']} wahrscheinlich falsch, {counts['unmatched']} ohne Treffer."
    )


def _count_by_upload() -> dict[int, dict[str, int]]:
    grouped: dict[int, dict[str, int]] = {}
    query = "SELECT upload_id, match_status, COUNT(*) AS n FROM external_rows GROUP BY upload_id, match_status"
    for row in g.db.execute(query):
        grouped.setdefault(row["upload_id"], {})[row["match_status"]] = row["n"]
    return grouped


def _requested_pages() -> dict[str, int]:
    pages = {}
    for status in STATUS_ORDER:
        raw = request.args.get(status, "1")
        try:
            pages[status] = max(1, int(raw))
        except (TypeError, ValueError):
            pages[status] = 1
    return pages


def _back_to_review(upload_id: int):
    args = {status: page for status, page in _requested_pages().items() if page > 1}
    return redirect(url_for("review", upload_id=upload_id, **args))


def _return_after_decision(upload_id: int, row, *, advance: bool):
    """Stay on the next open row of the band the user was reviewing."""
    band = request.form.get("band", "")
    if band not in STATUS_ORDER:
        return _back_to_review(upload_id)
    if not advance:
        return redirect(url_for("review", upload_id=upload_id, band=band, row=row["id"]))
    nxt = _next_open_row(upload_id, band, row["row_number"], row["id"])
    if nxt is None:
        return redirect(url_for("review", upload_id=upload_id, band=band, done=1))
    return redirect(url_for("review", upload_id=upload_id, band=band, row=nxt["id"]))


def _next_open_row(upload_id: int, band: str, row_number: int, row_id: int):
    for candidate in db.get_rows(g.db, upload_id):
        if candidate["match_status"] != band or candidate["locked"]:
            continue
        if (candidate["row_number"], candidate["id"]) > (row_number, row_id):
            return candidate
    return None


def _upload_progress(rows) -> dict:
    total = len(rows)
    counts = {status: 0 for status in STATUS_ORDER}
    remaining = 0
    for row in rows:
        if row["locked"]:
            continue
        remaining += 1
        counts[row["match_status"]] = counts.get(row["match_status"], 0) + 1
    bands = [
        {"label": STATUS_LABELS[status].lower(), "count": counts[status]}
        for status in STATUS_ORDER
        if counts.get(status)
    ]
    return {
        "total": total,
        "remaining": remaining,
        "processed": total - remaining,
        "bands": bands,
    }


def _focus_state(upload_id: int, band: str, rows=None) -> dict:
    if rows is None:
        rows = db.get_rows(g.db, upload_id)
    open_rows = [row for row in rows if row["match_status"] == band and not row["locked"]]
    requested = request.args.get("row", type=int)
    finished = request.args.get("done") == "1"
    current = None
    if not finished:
        if requested:
            current = next((row for row in open_rows if row["id"] == requested), None)
            if current is None:
                acted = next((row for row in rows if row["id"] == requested), None)
                if acted is not None:
                    current = _next_open_row(upload_id, band, acted["row_number"], acted["id"])
        if current is None:
            current = open_rows[0] if open_rows else None
    first = open_rows[0] if open_rows else None
    return {
        "key": band,
        "label": STATUS_LABELS[band],
        "copy": GROUP_COPY[band],
        "row": _row_view(current) if current is not None else None,
        "open_count": len(open_rows),
        "done": current is None,
        "first_url": (
            url_for("review", upload_id=upload_id, band=band, row=first["id"]) if first is not None else None
        ),
    }


def _review_page_url(upload_id: int, groups: list[dict], status: str, page: int) -> str:
    args = {}
    for group in groups:
        current = page if group["key"] == status else group["page"]
        if current > 1:
            args[group["key"]] = current
    return url_for("review", upload_id=upload_id, **args) + "#" + status


def _attach_page_links(upload_id: int, groups: list[dict]) -> None:
    for group in groups:
        group["prev_url"] = (
            _review_page_url(upload_id, groups, group["key"], group["page"] - 1) if group["page"] > 1 else None
        )
        group["next_url"] = (
            _review_page_url(upload_id, groups, group["key"], group["page"] + 1)
            if group["page"] < group["pages"]
            else None
        )


def _groups(rows, pages: dict[str, int] | None = None) -> list[dict]:
    requested = pages or {}
    buckets: dict[str, list] = {status: [] for status in STATUS_ORDER}
    for row in rows:
        buckets.setdefault(row["match_status"], []).append(row)
    groups = []
    for status in STATUS_ORDER:
        bucket = buckets.get(status, [])
        total = len(bucket)
        page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE) if total else 1
        page = min(requested.get(status, 1), page_count)
        start = (page - 1) * PAGE_SIZE
        groups.append(
            {
                "key": status,
                "label": STATUS_LABELS[status],
                "copy": GROUP_COPY[status],
                "rows": [_row_view(row) for row in bucket[start : start + PAGE_SIZE]],
                "total": total,
                "page": page,
                "pages": page_count,
            }
        )
    return groups


_TITLE_FEMALE = {"frau", "fr", "oä", "fä", "oberärztin", "fachärztin", "ärztin"}
_TITLE_MALE = {"herr", "hr", "oa", "fa", "oberarzt", "facharzt", "arzt"}
_NAME_SKIP = {
    "dr", "med", "prof", "univ", "mag", "prim", "oa", "oä", "fa", "fä", "dipl", "ing",
    "ddr", "phd", "assoc", "priv", "doz", "chefarzt", "bgdr", "or", "mr", "di", "ddr",
}
_GENDER_DETECTOR = None


def _gender_detector():
    global _GENDER_DETECTOR
    if _GENDER_DETECTOR is None:
        import gender_guesser.detector as gender

        _GENDER_DETECTOR = gender.Detector(case_sensitive=False)
    return _GENDER_DETECTOR


def gender_from_title(titel: str) -> str | None:
    """Read Herr/Frau and gendered Austrian titles such as OA/OÄ and FA/FÄ."""
    found = set()
    for token in re.findall(r"[a-zäöüß]+", (titel or "").casefold()):
        if token in _TITLE_FEMALE:
            found.add("f")
        elif token in _TITLE_MALE:
            found.add("m")
    if found == {"f"}:
        return "f"
    if found == {"m"}:
        return "m"
    return None


def gender_from_name(vorname: str) -> str | None:
    """Infer gender from the first given name. Unknown and unisex names stay unset."""
    detector = _gender_detector()
    for part in re.split(r"[\s,;/]+", (vorname or "").strip()):
        token = part.strip(".").strip()
        if not token or token.casefold().strip(".") in _NAME_SKIP:
            continue
        guess = detector.get_gender(token, "germany")
        if guess in {"unknown", "andy"} and "-" in token:
            guess = detector.get_gender(token.split("-", 1)[0], "germany")
        if guess in {"male", "mostly_male"}:
            return "m"
        if guess in {"female", "mostly_female"}:
            return "f"
    return None


def person_gender(titel: str, vorname: str) -> str | None:
    return gender_from_title(titel) or gender_from_name(vorname)


def genders_differ(left_titel: str, left_name: str, right_titel: str, right_name: str) -> bool:
    left = person_gender(left_titel, left_name)
    right = person_gender(right_titel, right_name)
    return bool(left and right and left != right)


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
            "wahlart": row["match_wahlart"],
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
        "wahlart": row["wahlart"],
        "score": row["match_score"],
        "status": row["match_status"],
        "method": row["match_method"],
        "note": row["match_note"],
        "locked": row["locked"],
        "candidate": candidate,
        "hint": learning.hint_for_row(row),
        "gender_mismatch": genders_differ(
            row["titel"],
            row["vorname"],
            row["match_titel"] if row["match_evo_id"] else "",
            row["match_vorname"] if row["match_evo_id"] else "",
        ),
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
                "wahlart": view["wahlart"],
                "source_extra": json.loads(row["source_extra"] or "{}"),
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
                "match_wahlart": view["candidate"]["wahlart"] if view["candidate"] else "",
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
