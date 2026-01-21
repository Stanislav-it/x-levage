from __future__ import annotations
import os
import sqlite3
import time
import math
from typing import List, Tuple, Optional
from datetime import datetime
from email.message import EmailMessage
import smtplib
from urllib.parse import urlencode, quote

import requests
from flask import (
    Flask, abort, flash, g, jsonify, redirect, render_template,
    request, session, url_for
)
from flask import current_app

APP_DIR = os.path.abspath(os.path.dirname(__file__))

# ---------------------------------------------------------------------------
# Storage paths
#
# Render notes:
# - Attach a Persistent Disk and mount it (recommended mount path: /var/data).
# - Set DATA_DIR=/var/data in Render Environment Variables.
# - The app stores SQLite under ${DATA_DIR}/instance/app.db.
#
# IMPORTANT:
# If you set DATA_DIR but forget to attach the disk (or mount path differs),
# Render will NOT allow writing to /var/data and the app will crash.
# To be resilient, we automatically fall back to a writable local directory.
# ---------------------------------------------------------------------------

def _first_writable_dir(candidates: List[str]) -> str:
    """Return the first directory we can create/write to."""
    for d in candidates:
        if not d:
            continue
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".write_test")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe)
            return d
        except Exception:
            continue
    # Last resort: app directory instance (may still fail, but then error is real)
    d = os.path.join(APP_DIR, "instance")
    os.makedirs(d, exist_ok=True)
    return d


def resolve_storage_paths() -> Tuple[str, str]:
    """Return (instance_dir, db_path) using env vars with safe fallbacks."""
    data_dir = (os.environ.get("DATA_DIR") or "").strip()
    desired_instance = os.path.join(data_dir, "instance") if data_dir else ""

    # Pick first writable among: desired (disk), app-local, /tmp
    instance_dir = _first_writable_dir([
        desired_instance,
        os.path.join(APP_DIR, "instance"),
        os.path.join("/tmp", "instance"),
    ])

    if desired_instance and os.path.abspath(instance_dir) != os.path.abspath(desired_instance):
        print(
            f"[WARN] DATA_DIR is set to '{data_dir}', but it is not writable. "
            f"Falling back to '{instance_dir}'. To enable persistence on Render, "
            "attach a Persistent Disk mounted at the same path and redeploy."
        )

    default_db_path = os.path.join(instance_dir, "app.db")
    db_path = (os.environ.get("SQLITE_DB_PATH") or default_db_path).strip()

    # Allow relative DB paths for convenience (e.g. SQLITE_DB_PATH=instance/app.db)
    if db_path and not os.path.isabs(db_path):
        db_path = os.path.join(APP_DIR, db_path)

    # Ensure parent exists (may be different if SQLITE_DB_PATH overrides)
    try:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    except Exception:
        # If override points somewhere unwritable, fall back to instance_dir
        db_path = default_db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    return instance_dir, db_path


def create_app():
    instance_dir, db_path = resolve_storage_paths()
    app = Flask(__name__, instance_path=instance_dir, instance_relative_config=True)
    debug = str(os.environ.get("FLASK_DEBUG", "")).strip().lower() in {"1", "true", "yes"}

    app.config.update(
        # Storage
        DB_PATH=db_path,

        # Security
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-key-change-me"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not debug,  # Render uses HTTPS; secure cookies in production.

        # Admin
        ADMIN_USER=os.environ.get("ADMIN_USER", "admin"),
        ADMIN_PASS=os.environ.get("ADMIN_PASS", "admin"),

        # Lead persistence on disk (in addition to SQLite)
        # These directories will be created under the DATA_DIR root if available
        # (recommended on Render: /var/data).
        LEADS_DIR=os.environ.get("LEADS_DIR", os.path.join(os.path.dirname(instance_dir), "leads")),
        # Optional: append-only JSONL archive (one JSON object per line).
        # If not provided, defaults to ${LEADS_DIR}/leads.jsonl
        LEADS_JSONL_PATH=os.environ.get("LEADS_JSONL_PATH", ""),
        MAIL_ARCHIVE_DIR=os.environ.get("MAIL_ARCHIVE_DIR", os.path.join(os.path.dirname(instance_dir), "mail_archive")),

        # Branding / contact
        SITE_NAME=os.environ.get("SITE_NAME", "X‑LEVAGE"),
        BRAND=os.environ.get("BRAND", "X‑LEVAGE"),
        CONTACT_EMAIL=os.environ.get("CONTACT_EMAIL", "xlevage@gmail.com"),
        CONTACT_PHONE=os.environ.get("CONTACT_PHONE", "+48 518 151 673"),
        INSTAGRAM_HANDLE=os.environ.get("INSTAGRAM_HANDLE", "xestetik"),
        INSTAGRAM_URL=os.environ.get(
            "INSTAGRAM_URL",
            "https://www.instagram.com/xestetik?utm_source=ig_web_button_share_sheet&igsh=ZDNlZDc0MzIxNw==",
        ),
        FACEBOOK_URL=os.environ.get(
            "FACEBOOK_URL",
            "https://www.facebook.com/lasertulowyxlevage",
        ),
        # Contact form email delivery
        MAIL_TO=os.environ.get("MAIL_TO", "xlevage@gmail.com"),
        SMTP_HOST=os.environ.get("SMTP_HOST", ""),
        SMTP_PORT=int(os.environ.get("SMTP_PORT", "587")),
        SMTP_USER=os.environ.get("SMTP_USER", ""),
        SMTP_PASS=os.environ.get("SMTP_PASS", ""),
        SMTP_FROM=os.environ.get("SMTP_FROM", ""),
        SMTP_TLS=str(os.environ.get("SMTP_TLS", "1")).strip().lower() in {"1", "true", "yes"},

        # External requests
        NOMINATIM_USER_AGENT=os.environ.get(
            "NOMINATIM_USER_AGENT",
            "xlevage-site/1.0 (contact: xlevage@gmail.com)",
        ),
    )

    # If JSONL path is not explicitly set, default it under LEADS_DIR.
    if not (app.config.get("LEADS_JSONL_PATH") or "").strip():
        app.config["LEADS_JSONL_PATH"] = os.path.join(app.config.get("LEADS_DIR") or "", "leads.jsonl")
    # Ensure instance dir exists (resolve_storage_paths already does, but keep safe)
    os.makedirs(instance_dir, exist_ok=True)
    # Ensure data directories exist (best-effort)
    for _d in (app.config.get('LEADS_DIR'), app.config.get('MAIL_ARCHIVE_DIR')):
        try:
            if _d:
                os.makedirs(_d, exist_ok=True)
        except Exception as _exc:
            print(f"[WARN] Could not create data dir {_d}: {_exc}")


    # Basic safety: show a warning in logs if you forgot to configure secrets.
    if not debug:
        if app.config["SECRET_KEY"] == "dev-secret-key-change-me":
            print("[WARN] SECRET_KEY is using the default value. Set it in Render Environment Variables.")
        if app.config["ADMIN_USER"] == "admin" and app.config["ADMIN_PASS"] == "admin":
            print("[WARN] Admin credentials are still admin/admin. Change ADMIN_USER and ADMIN_PASS.")

    @app.before_request
    def _db_before_request():
        g.db = get_db()

    @app.teardown_appcontext
    def _db_teardown(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with app.app_context():
        init_db()

    # ---------- Helpers ----------
    def is_admin():
        return bool(session.get("is_admin"))

    def require_admin():
        if not is_admin():
            return redirect(url_for("admin_login", next=request.path))

    def mailto_link(to_email: str, subject: str = "", body: str = "") -> str:
        """Build a safe mailto: URL for templates."""
        to_email = (to_email or "").strip()
        if not to_email:
            return ""
        q = {}
        if subject:
            q["subject"] = subject
        if body:
            q["body"] = body
        query = urlencode(q, quote_via=quote) if q else ""
        return f"mailto:{to_email}?{query}" if query else f"mailto:{to_email}"

    def gmail_compose_link(to_email: str, subject: str = "", body: str = "") -> str:
        """Build a Gmail web compose URL as a cross-platform fallback.

        Note: This opens Gmail in the browser (or Gmail app if the OS routes it).
        """
        to_email = (to_email or "").strip()
        if not to_email:
            return ""
        params = {
            'view': 'cm',
            'fs': '1',
            'to': to_email,
        }
        if subject:
            params['su'] = subject
        if body:
            params['body'] = body
        query = urlencode(params, quote_via=quote)
        return f"https://mail.google.com/mail/?{query}"


    def archive_lead_to_disk(*, lead_id: int, created_at: str, name: str, email: str, phone: str, message: str) -> None:
        """Persist the lead as a JSON file on disk (optional).

        This is useful on Render when you want a simple file-level archive in addition to SQLite.
        It is best-effort and must never break the user flow.
        """
        leads_dir = (app.config.get('LEADS_DIR') or '').strip()
        jsonl_path = (app.config.get('LEADS_JSONL_PATH') or '').strip()
        if not leads_dir and not jsonl_path:
            return
        try:
            if leads_dir:
                os.makedirs(leads_dir, exist_ok=True)
            if jsonl_path:
                os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
            safe_ts = created_at.replace(':', '').replace('-', '').replace('T', '_')
            import json
            payload = {
                'id': int(lead_id),
                'created_at_utc': created_at,
                'name': name,
                'email': email,
                'phone': phone,
                'message': message,
            }

            # 1) Per-lead JSON file (easy to browse)
            if leads_dir:
                fn = f"lead_{lead_id}_{safe_ts}.json"
                path = os.path.join(leads_dir, fn)
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)

            # 2) Append-only JSONL file (easy to backup/grep)
            if jsonl_path:
                with open(jsonl_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(payload, ensure_ascii=False))
                    f.write("\n")
        except Exception as exc:
            print(f"[WARN] Failed to archive lead to disk: {exc}")

    def send_lead_email(*, name: str, email: str, phone: str, message: str, lead_id: Optional[int] = None, created_at: Optional[str] = None) -> bool:
        """Send a contact form notification via SMTP.

        Delivery is best-effort: if SMTP is not configured or sending fails,
        the lead is still saved to SQLite and the user sees a success message.
        """

        mail_to = (app.config.get("MAIL_TO") or "").strip()
        smtp_host = (app.config.get("SMTP_HOST") or "").strip()
        smtp_user = (app.config.get("SMTP_USER") or "").strip()
        smtp_pass = (app.config.get("SMTP_PASS") or "").strip()
        smtp_from = (app.config.get("SMTP_FROM") or "").strip() or smtp_user
        smtp_port = int(app.config.get("SMTP_PORT") or 587)
        smtp_tls = bool(app.config.get("SMTP_TLS"))

        # If SMTP isn't configured, silently skip.
        if not (mail_to and smtp_host and smtp_from):
            return False

        try:
            msg = EmailMessage()
            msg["Subject"] = f"Nowe zapytanie — {app.config.get('BRAND', 'X‑LEVAGE')}"
            msg["From"] = smtp_from
            msg["To"] = mail_to

            lines = [
                "Nowe zapytanie z formularza kontaktowego:",
                "",
                f"Imię i nazwisko: {name or '-'}",
                f"E‑mail: {email or '-'}",
                f"Telefon: {phone or '-'}",
                "",
                "Wiadomość:",
                message or "-",
                "",
                f"Czas (UTC): {datetime.utcnow().isoformat(timespec='seconds')}",
            ]
            msg.set_content("\n".join(lines))

            # Best-effort archive of the raw email on disk (optional)
            try:
                archive_dir = (app.config.get('MAIL_ARCHIVE_DIR') or '').strip()
                if archive_dir and lead_id is not None and created_at:
                    os.makedirs(archive_dir, exist_ok=True)
                    safe_ts = created_at.replace(':', '').replace('-', '').replace('T', '_')
                    eml_path = os.path.join(archive_dir, f"lead_{lead_id}_{safe_ts}.eml")
                    with open(eml_path, 'wb') as f:
                        f.write(msg.as_bytes())
            except Exception as _exc:
                print(f"[WARN] Failed to archive email: {_exc}")

            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                server.ehlo()
                if smtp_tls:
                    server.starttls()
                    server.ehlo()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            return True
        except Exception as exc:
            print(f"[WARN] Failed to send lead email: {exc}")
            return False

    # ---------- Public ----------
    @app.get("/")
    def index():
        effects = list_static_images("efekty_zabiegow")
        devices = list_static_images("fotos")
        stats = {
            "pro_wavelength": "1927 nm",
            "erbo_wavelength": "1550 nm + 1927 nm",
        }
        return render_template("index.html", effects=effects, devices=devices, stats=stats)

    @app.get("/laser-tulowy-x-levage-pro")
    def pro():
        effects = list_static_images("efekty_zabiegow")
        return render_template("pro.html", effects=effects)

    @app.get("/x-levage-erbo")
    def erbo():
        effects = list_static_images("efekty_zabiegow")
        return render_template("erbo.html", effects=effects)

    @app.get("/gabinet")
    def gabinet():
        # Public page: by default show all official locations.
        # view: all | ambassadors | authorized
        view = request.args.get("view", "all")
        q = request.args.get("q", "").strip()
        clinics = search_clinics(view=view, q=q, limit=500)
        return render_template("gabinet.html", clinics=clinics, view=view, q=q)

    @app.get("/umow-prezentacje")
    def prezentacja():
        # Only ambassadors (incl. Showroom) offer free device presentations.
        ambassador_clinics = search_clinics(view="ambassadors", q="", limit=500)
        return render_template("prezentacja.html", ambassador_clinics=ambassador_clinics)

    @app.post("/umow-prezentacje")
    def prezentacja_post():
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        city = request.form.get("city", "").strip()
        preferred_date = request.form.get("preferred_date", "").strip()
        preferred_clinic = request.form.get("preferred_clinic", "").strip()
        note = request.form.get("message", "").strip()

        if not email and not phone:
            flash("Podaj e‑mail lub telefon, abyśmy mogli się skontaktować.", "error")
            return redirect(url_for("prezentacja"))

        # Store extra fields inside the lead message (single table column).
        lines = [
            "Umów prezentację urządzenia",
            "",
            f"Miasto: {city or '-'}",
            f"Preferowany termin: {preferred_date or '-'}",
            f"Preferowany gabinet: {preferred_clinic or '-'}",
            "",
            "Dodatkowa wiadomość:",
            note or "-",
        ]
        message = "\n".join(lines)

        db = get_db()
        created_at = datetime.utcnow().isoformat(timespec="seconds")
        cur = db.execute(
            "INSERT INTO leads(name,email,phone,message,created_at) VALUES(?,?,?,?,?)",
            (name, email, phone, message, created_at),
        )
        lead_id = cur.lastrowid
        db.commit()

        # Best-effort file archive on disk (optional).
        archive_lead_to_disk(lead_id=lead_id, created_at=created_at, name=name, email=email, phone=phone, message=message)

        # Best-effort email notification (if SMTP configured).
        send_lead_email(name=name, email=email, phone=phone, message=message, lead_id=lead_id, created_at=created_at)

        flash("Dziękujemy. Skontaktujemy się wkrótce.", "success")
        return redirect(url_for("prezentacja"))

    @app.get("/api/clinics")
    def api_clinics():
        view = request.args.get("view", "all")
        q = request.args.get("q", "").strip()
        clinics = search_clinics(view=view, q=q, limit=2000)
        return jsonify({"clinics": clinics})

    @app.post("/lead")
    def lead():
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        message = request.form.get("message", "").strip()

        if not email and not phone:
            flash("Podaj e‑mail lub telefon, abyśmy mogli się skontaktować.", "error")
            return redirect(request.referrer or url_for("index"))

        db = get_db()
        created_at = datetime.utcnow().isoformat(timespec="seconds")
        cur = db.execute(
            "INSERT INTO leads(name,email,phone,message,created_at) VALUES(?,?,?,?,?)",
            (name, email, phone, message, created_at),
        )
        lead_id = cur.lastrowid
        db.commit()

        # Best-effort file archive on disk (optional).
        archive_lead_to_disk(lead_id=lead_id, created_at=created_at, name=name, email=email, phone=phone, message=message)

        # Best-effort email notification (if SMTP configured).
        send_lead_email(name=name, email=email, phone=phone, message=message, lead_id=lead_id, created_at=created_at)

        flash("Dziękujemy. Skontaktujemy się wkrótce.", "success")
        return redirect(request.referrer or url_for("index"))

    # ---------- Policies ----------
    @app.get("/policies/<slug>")
    def policies(slug):
        allowed = {"privacy", "cookies", "terms", "disclaimer", "rodo"}
        if slug not in allowed:
            abort(404)
        return render_template(f"policies/{slug}.html")

    # ---------- Admin ----------
    @app.get("/admin/login")
    def admin_login():
        return render_template("admin/login.html", next=request.args.get("next", url_for("admin_dashboard")))

    @app.post("/admin/login")
    def admin_login_post():
        username = (request.form.get("username", "") or "").strip()
        password = (request.form.get("password", "") or "").strip()
        nxt = request.form.get("next") or url_for("admin_dashboard")
        if username == app.config.get("ADMIN_USER") and password == app.config.get("ADMIN_PASS"):
            session["is_admin"] = True
            flash("Zalogowano.", "success")
            return redirect(nxt)
        flash("Nieprawidłowy login lub hasło.", "error")
        return redirect(url_for("admin_login", next=nxt))

    @app.post("/admin/logout")
    def admin_logout():
        session.clear()
        flash("Wylogowano.", "success")
        return redirect(url_for("index"))

    @app.get("/admin")
    def admin_dashboard():
        ra = require_admin()
        if ra: return ra
        view = request.args.get("view", "all")
        q = request.args.get("q", "").strip()
        clinics = search_clinics(view=view, q=q, limit=2000)
        return render_template("admin/dashboard.html", clinics=clinics, view=view, q=q)

    @app.get("/admin/clinics/new")
    def admin_clinic_new():
        ra = require_admin()
        if ra: return ra
        return render_template("admin/clinic_form.html", clinic=None)

    @app.post("/admin/clinics/new")
    def admin_clinic_new_post():
        ra = require_admin()
        if ra: return ra
        form = clinic_from_form()
        cid = upsert_clinic(None, form, geocode_if_missing=True)
        flash("Dodano gabinet.", "success")
        return redirect(url_for("admin_dashboard") + f"?highlight={cid}")

    @app.get("/admin/clinics/<int:cid>/edit")
    def admin_clinic_edit(cid):
        ra = require_admin()
        if ra: return ra
        clinic = get_clinic(cid)
        if not clinic:
            abort(404)
        return render_template("admin/clinic_form.html", clinic=clinic)

    @app.post("/admin/clinics/<int:cid>/edit")
    def admin_clinic_edit_post(cid):
        ra = require_admin()
        if ra: return ra
        clinic = get_clinic(cid)
        if not clinic:
            abort(404)
        form = clinic_from_form()
        upsert_clinic(cid, form, geocode_if_missing=True)
        flash("Zapisano zmiany.", "success")
        return redirect(url_for("admin_dashboard") + f"?highlight={cid}")

    @app.post("/admin/clinics/<int:cid>/delete")
    def admin_clinic_delete(cid):
        ra = require_admin()
        if ra: return ra
        db = get_db()
        db.execute("DELETE FROM clinics WHERE id=?", (cid,))
        db.commit()
        flash("Usunięto.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.get("/admin/import")
    def admin_import():
        ra = require_admin()
        if ra: return ra
        return render_template("admin/import.html")

    @app.post("/admin/import")
    def admin_import_post():
        ra = require_admin()
        if ra: return ra
        raw = request.form.get("raw", "").strip()
        default_type = request.form.get("default_type", "authorized")
        created, updated, skipped = bulk_import(raw, default_type=default_type)
        flash(f"Import zakończony: dodano {created}, zaktualizowano {updated}, pominięto {skipped}.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.get("/admin/notifications")
    def admin_notifications():
        """Admin view: list contact form submissions (leads).

        This replaces email delivery as the primary notification channel.
        """
        ra = require_admin()
        if ra:
            return ra

        q = (request.args.get("q", "") or "").strip()
        try:
            page = int(request.args.get("page", "1") or 1)
        except Exception:
            page = 1
        page = max(1, page)
        per_page = 50
        offset = (page - 1) * per_page

        db = get_db()
        where = []
        params: list = []
        if q:
            where.append("(name LIKE ? OR email LIKE ? OR phone LIKE ? OR message LIKE ?)")
            qq = f"%{q}%"
            params.extend([qq, qq, qq, qq])

        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        total = db.execute(f"SELECT COUNT(1) AS c FROM leads{where_sql}", params).fetchone()["c"]
        rows = db.execute(
            f"SELECT * FROM leads{where_sql} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()

        leads = [row_to_dict(r) for r in rows]
        total_pages = max(1, math.ceil((total or 0) / per_page))
        if page > total_pages:
            page = total_pages

        return render_template(
            "admin/notifications.html",
            leads=leads,
            q=q,
            page=page,
            total_pages=total_pages,
            total=total,
            per_page=per_page,
        )

    @app.post("/admin/geocode/<int:cid>")
    def admin_geocode(cid):
        ra = require_admin()
        if ra: return ra
        clinic = get_clinic(cid)
        if not clinic:
            abort(404)
        lat, lon = geocode_address(clinic["address"])
        if lat and lon:
            db = get_db()
            db.execute("UPDATE clinics SET lat=?, lon=?, updated_at=? WHERE id=?",
                       (lat, lon, datetime.utcnow().isoformat(timespec="seconds"), cid))
            db.commit()
            return jsonify({"ok": True, "lat": lat, "lon": lon})
        return jsonify({"ok": False}), 400

    # ---------- Template globals ----------
    @app.context_processor
    def inject_globals():
        return {
            "SITE_NAME": app.config["SITE_NAME"],
            "BRAND": app.config["BRAND"],
            "CONTACT_EMAIL": app.config["CONTACT_EMAIL"],
            "CONTACT_PHONE": app.config["CONTACT_PHONE"],
            "INSTAGRAM_HANDLE": app.config.get("INSTAGRAM_HANDLE", ""),
            "INSTAGRAM_URL": app.config.get("INSTAGRAM_URL", ""),
            "FACEBOOK_URL": app.config.get("FACEBOOK_URL", ""),
            "is_admin": is_admin(),
            "mailto_link": mailto_link,
            "gmail_compose_link": gmail_compose_link,
            "CURRENT_YEAR": datetime.utcnow().year,
        }

    return app

# -------------------- DB --------------------
def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db_path = current_app.config.get("DB_PATH")
        db = sqlite3.connect(db_path, check_same_thread=False)
        db.row_factory = sqlite3.Row
        # Improve concurrency for multi-request workloads.
        try:
            db.execute("PRAGMA journal_mode=WAL;")
            db.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass
        g._db = db
    return db

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS clinics(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL, -- ambassadors|authorized
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            city TEXT,
            phone TEXT,
            website TEXT,
            notes TEXT,
            lat REAL,
            lon REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS geocode_cache(
            address TEXT PRIMARY KEY,
            lat REAL,
            lon REAL,
            updated_at TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS leads(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            phone TEXT,
            message TEXT,
            created_at TEXT NOT NULL
        )
    """)
    db.commit()

    # Ensure the public "Autoryzowane Gabinety" list is present.
    # This replaces any demo/ambassador content and keeps only the official list.
    sync_official_clinics(db)


def official_clinics_list():
    """Canonical list for the public map.

    We keep two categories:
    - kind='ambassadors' for locations where a free device presentation is available.
    - kind='authorized' for all other authorized locations.

    lat/lon are resolved automatically on first run via Nominatim (and cached).
    """
    # Ambassadors list as provided by the client:
    # Showroom + 4,5,8,10,13,14,16,19,20,21,22
    return [
        # 1 (renamed)
        {
            "kind": "ambassadors",
            "name": "Showroom Firmowy",
            "address": "Zabrska 15, 40-101 Katowice, Polska",
            "city": "Katowice",
            "phone": "503551055",
            "lat": 50.263068,
            "lon": 19.012763,
        },

        # 2
        {
            "kind": "authorized",
            "name": "Allure Strefa Piękna",
            "address": "Aleja Wojska Polskiego 70C, Zielona Góra, Polska",
            "city": "Zielona Góra",
            "phone": "+48600331773",
            "lat": 51.937828,
            "lon": 15.488992,
        },
        # 3
        {
            "kind": "authorized",
            "name": "The Beauty Aleksandra Szymczak",
            "address": "Młynarska 119, Kalisz, Polska",
            "city": "Kalisz",
            "phone": "606911114",
            "lat": 51.751345,
            "lon": 18.069903,
        },

        # 4
        {
            "kind": "ambassadors",
            "name": "Salon Pretty WOMEN",
            "address": "Okrzei 39, 87-800 Włocławek, Polska",
            "city": "Włocławek",
            "phone": "604446352",
            "lat": 52.6489,
            "lon": 19.065977,
        },
        # 5
        {
            "kind": "ambassadors",
            "name": "EK Medica Clinic",
            "address": "Lubartowska 77, Lublin, Polska",
            "city": "Lublin",
            "phone": "531090033",
            "lat": 51.256674,
            "lon": 22.571279,
        },
        # 6
        {
            "kind": "authorized",
            "name": "Aurevia Clinic",
            "address": "Rynkowa 96, Przeźmierowo, Polska",
            "city": "Przeźmierowo",
            "phone": "508522474",
            "lat": 52.426882,
            "lon": 16.7845,
        },
        # 7
        {
            "kind": "authorized",
            "name": "Beauty Spa Iwona Olszowiak",
            "address": "Sienkiewicza 21, Świeradów-Zdrój, Polska",
            "city": "Świeradów-Zdrój",
            "phone": "662070569",
            "lat": 50.908304,
            "lon": 15.329688,
        },
        # 8
        {
            "kind": "ambassadors",
            "name": "Kosmetologia Trychologia Paulina Wiszniowska",
            "address": "Morelowa 34, Zielona Góra, Polska",
            "city": "Zielona Góra",
            "phone": "531431273",
            "lat": 51.931736,
            "lon": 15.516633,
        },
        # 9
        {
            "kind": "authorized",
            "name": "Centrum Urody Chłodnamed",
            "address": "Chłodna 26, Radom, Polska",
            "city": "Radom",
            "phone": "502166165",
            "lat": 51.407659,
            "lon": 21.135747,
        },
        # 10
        {
            "kind": "ambassadors",
            "name": "Gacka Permanent & Estetyka",
            "address": "Paprocańska 47, Tychy, Polska",
            "city": "Tychy",
            "phone": "508175609",
            "lat": 50.106309,
            "lon": 19.001723,
        },
        # 11
        {
            "kind": "authorized",
            "name": "Beauty Home Kosmetologia",
            "address": "Ochabska 5, Kiczyce, Skoczów, Polska",
            "city": "Kiczyce (Skoczów)",
            "phone": "505633026",
            "lat": 49.822517,
            "lon": 18.799859,
        },
        # 12
        {
            "kind": "authorized",
            "name": "Centrum Urody Roksana Wesołowska",
            "address": "Długosza 33, Człuchów, Polska",
            "city": "Człuchów",
            "phone": "794433098",
            "lat": 53.666538,
            "lon": 17.357449,
        },
        # 13
        {
            "kind": "ambassadors",
            "name": "Permanentny Martinez",
            "address": "Granitowa 6/1, Smolec, Polska",
            "city": "Smolec",
            "phone": "577019130",
            "lat": 51.08367,
            "lon": 16.909502,
        },
        # 14
        {
            "kind": "ambassadors",
            "name": "Salon Urody Czapla Iwona Nalikowska",
            "address": "Pomorska 64, Czaple, Polska",
            "city": "Czaple",
            "phone": "530526227",
            "lat": 54.360295,
            "lon": 18.43239,
        },
        # 15
        {
            "kind": "authorized",
            "name": "Akademia Piękna Health and Beauty",
            "address": "Trablice 32, Trablice, Polska",
            "city": "Trablice",
            "phone": "509837346",
            "lat": 51.348981,
            "lon": 21.110435,
        },
        # 16
        {
            "kind": "ambassadors",
            "name": "Holies Aesthetic",
            "address": "Sąsiedzka 13a, Poznań, Polska",
            "city": "Poznań",
            "phone": "537233229",
            "lat": 52.355149,
            "lon": 16.855358,
        },
        # 17
        {
            "kind": "authorized",
            "name": "Skwarczyńska Skin Clinic & Academy",
            "address": "Hierowskiego 37, Tychy, Polska",
            "city": "Tychy",
            "phone": "783526204",
            "lat": 50.114653,
            "lon": 18.974568,
        },
        # 18
        {
            "kind": "authorized",
            "name": "Galeria Urody Roza",
            "address": "Grunwaldzka 55/18, Płońsk, Polska",
            "city": "Płońsk",
            "phone": "509833765",
            "lat": 52.629147,
            "lon": 20.373171,
        },
        # 19
        {
            "kind": "ambassadors",
            "name": "Salon Victoria",
            "address": "Kościuszki 12, Ropczyce, Polska",
            "city": "Ropczyce",
            "phone": "+48533014472",
            "lat": 50.05279,
            "lon": 21.60739,
        },
        # 20
        {
            "kind": "ambassadors",
            "name": "Studio Urody Anna Kaczmarek",
            "address": "Adama Mickiewicza 15, Nowy Tomyśl, Polska",
            "city": "Nowy Tomyśl",
            "phone": "697384364",
            "lat": 52.317275,
            "lon": 16.13163,
        },
        # 21
        {
            "kind": "ambassadors",
            "name": "Kowalewska Medycyna Estetyczna",
            "address": "Książkowa 9G, Warszawa, Polska",
            "city": "Warszawa",
            "phone": "502431843",
            "lat": 52.33203,
            "lon": 20.939324,
        },
        # 22
        {
            "kind": "ambassadors",
            "name": "Instytut Urody i Makijażu Permanentnego Wioletta Kolasa",
            "address": "Kopernika 7a, Wieliczka, Polska",
            "city": "Wieliczka",
            "phone": "501232995",
            "lat": 49.981356,
            "lon": 20.059356,
        },
    ]


def sync_official_clinics(db):
    """Synchronize the clinics table with the official list.

    Rules:
    - Keep *only* entries present in `official_clinics_list()`.
    - Enforce the exact `kind` (ambassadors/authorized) from the official list.
    - Best-effort geocode missing coordinates (cached in `geocode_cache`).
    """
    try:
        rows = db.execute("SELECT id, kind, name, address, city, phone, lat, lon FROM clinics").fetchall()
    except Exception:
        return

    official = official_clinics_list()
    allowed_keys = set(
        (
            (c.get("name", "") or "").strip(),
            (c.get("address", "") or "").strip(),
            (c.get("city", "") or "").strip(),
            (c.get("phone", "") or "").strip(),
        )
        for c in official
    )

    # Map key -> desired kind (so we can enforce categories).
    desired_kind = {
        (
            (c.get("name", "") or "").strip(),
            (c.get("address", "") or "").strip(),
            (c.get("city", "") or "").strip(),
            (c.get("phone", "") or "").strip(),
        ): (c.get("kind") or "authorized")
        for c in official
    }

    
    desired_coords = {
        (
            (c.get("name", "") or "").strip(),
            (c.get("address", "") or "").strip(),
            (c.get("city", "") or "").strip(),
            (c.get("phone", "") or "").strip(),
        ): (c.get("lat"), c.get("lon"))
        for c in official
    }

    existing_keys = set()
    to_delete_ids = []
    for r in rows:
        key = (
            (r["name"] or "").strip(),
            (r["address"] or "").strip(),
            (r["city"] or "").strip(),
            (r["phone"] or "").strip(),
        )
        if key in allowed_keys:
            existing_keys.add(key)
            # Enforce official kind + coordinates.
            want = desired_kind.get(key, "authorized")
            latlon = desired_coords.get(key)
            want_lat = latlon[0] if latlon else None
            want_lon = latlon[1] if latlon else None

            need_kind = (r["kind"] != want)
            need_coords = (want_lat is not None and want_lon is not None and (r["lat"] != want_lat or r["lon"] != want_lon))

            if need_kind or need_coords:
                db.execute(
                    "UPDATE clinics SET kind=?, lat=?, lon=?, updated_at=? WHERE id=?",
                    (
                        want,
                        want_lat if want_lat is not None else r["lat"],
                        want_lon if want_lon is not None else r["lon"],
                        datetime.utcnow().isoformat(timespec="seconds"),
                        r["id"],
                    ),
                )
        else:
            # Remove any non-official entries, including ambassadors/demo.
            to_delete_ids.append(r["id"])

    if to_delete_ids:
        db.executemany("DELETE FROM clinics WHERE id=?", [(i,) for i in to_delete_ids])

    now = datetime.utcnow().isoformat(timespec="seconds")
    for c in official:
        key = (
            (c.get("name", "") or "").strip(),
            (c.get("address", "") or "").strip(),
            (c.get("city", "") or "").strip(),
            (c.get("phone", "") or "").strip(),
        )
        if key in existing_keys:
            continue
        db.execute(
            """INSERT INTO clinics(kind,name,address,city,phone,website,notes,lat,lon,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                (c.get("kind") or "authorized"),
                c["name"].strip(),
                c["address"].strip(),
                c.get("city", "").strip(),
                c.get("phone", "").strip(),
                c.get("website", "").strip(),
                c.get("notes", "").strip(),
                c.get("lat"),
                c.get("lon"),
                now,
                now,
            ),
        )

    db.commit()

    # Best-effort: geocode all official entries that do not have coordinates yet.
    try:
        rows = db.execute("SELECT id, address, lat, lon FROM clinics").fetchall()
        for r in rows:
            if r["lat"] and r["lon"]:
                continue
            lat, lon = geocode_address(r["address"])
            if lat and lon:
                db.execute(
                    "UPDATE clinics SET lat=?, lon=?, updated_at=? WHERE id=?",
                    (lat, lon, datetime.utcnow().isoformat(timespec="seconds"), r["id"]),
                )
        db.commit()
    except Exception as _exc:
        print(f"[WARN] Geocode sync failed: {_exc}")

def row_to_dict(row):
    if row is None: return None
    return {k: row[k] for k in row.keys()}

def get_clinic(cid: int):
    db = get_db()
    row = db.execute("SELECT * FROM clinics WHERE id=?", (cid,)).fetchone()
    return row_to_dict(row)

def search_clinics(view="all", q="", limit=500):
    db = get_db()
    where = []
    params = []
    if view == "authorized":
        where.append("kind=?")
        params.append("authorized")
    elif view == "ambassadors":
        where.append("kind=?")
        params.append("ambassadors")
    elif view == "ambassadors":
        where.append("kind=?")
        params.append("ambassadors")
    if q:
        where.append("(name LIKE ? OR address LIKE ? OR city LIKE ?)")
        qq = f"%{q}%"
        params.extend([qq, qq, qq])
    sql = "SELECT * FROM clinics"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY city IS NULL, city, name LIMIT ?"
    params.append(limit)
    rows = db.execute(sql, params).fetchall()
    return [row_to_dict(r) for r in rows]

def upsert_clinic(cid, data, geocode_if_missing=True):
    now = datetime.utcnow().isoformat(timespec="seconds")
    db = get_db()
    if geocode_if_missing and (not data.get("lat") or not data.get("lon")):
        lat, lon = geocode_address(data.get("address", ""))
        if lat and lon:
            data["lat"], data["lon"] = lat, lon
    if cid is None:
        cur = db.execute(
            """INSERT INTO clinics(kind,name,address,city,phone,website,notes,lat,lon,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data["kind"], data["name"], data["address"], data.get("city",""),
                data.get("phone",""), data.get("website",""), data.get("notes",""),
                data.get("lat"), data.get("lon"), now, now
            )
        )
        db.commit()
        return cur.lastrowid
    else:
        db.execute(
            """UPDATE clinics SET kind=?,name=?,address=?,city=?,phone=?,website=?,notes=?,lat=?,lon=?,updated_at=?
               WHERE id=?""",
            (
                data["kind"], data["name"], data["address"], data.get("city",""),
                data.get("phone",""), data.get("website",""), data.get("notes",""),
                data.get("lat"), data.get("lon"), now, cid
            )
        )
        db.commit()
        return cid

def clinic_from_form():
    def f(key, default=""):
        return (request.form.get(key, default) or "").strip()
    lat = f("lat")
    lon = f("lon")
    return {
        "kind": f("kind", "authorized") or "authorized",
        "name": f("name"),
        "address": f("address"),
        "city": f("city"),
        "phone": f("phone"),
        "website": f("website"),
        "notes": f("notes"),
        "lat": float(lat) if lat else None,
        "lon": float(lon) if lon else None,
    }

# -------------------- Geocoding --------------------
def geocode_address(address: str):
    address = (address or "").strip()
    if not address:
        return (None, None)

    # Improve hit-rate: if user provided a partial address, bias search to Poland.
    if "polska" not in address.lower() and "poland" not in address.lower():
        address_q = f"{address}, Polska"
    else:
        address_q = address

    db = get_db()
    cached = db.execute("SELECT lat, lon FROM geocode_cache WHERE address=?", (address,)).fetchone()
    if cached and cached["lat"] and cached["lon"]:
        return (cached["lat"], cached["lon"])

    # Polite Nominatim usage: one request per second and a valid UA.
    # IMPORTANT: prefer app config over env vars so the default UA configured
    # in create_app() is actually used in production.
    time.sleep(1.0)
    try:
        ua = (
            (current_app.config.get("NOMINATIM_USER_AGENT") if current_app else "")
            or os.environ.get("NOMINATIM_USER_AGENT", "")
            or "xlevage-site/1.0 (contact: xlevage@gmail.com)"
        )

        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "format": "json",
                "limit": 1,
                "q": address_q,
                "countrycodes": "pl",
                "addressdetails": 0,
            },
            headers={
                "User-Agent": ua,
                "Accept-Language": "pl",
            },
            timeout=12,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            _save_geocode_cache(address, None, None)
            return (None, None)
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        _save_geocode_cache(address, lat, lon)
        return (lat, lon)
    except Exception:
        _save_geocode_cache(address, None, None)
        return (None, None)

def _save_geocode_cache(address, lat, lon):
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO geocode_cache(address,lat,lon,updated_at) VALUES(?,?,?,?)",
        (address, lat, lon, datetime.utcnow().isoformat(timespec="seconds")),
    )
    db.commit()

# -------------------- Bulk import --------------------
def bulk_import(raw: str, default_type="authorized"):
    """
    Format (one clinic per line):
      name | address | city | phone | website | kind
    kind is optional: ambassadors/authorized
    """
    created = updated = skipped = 0
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            skipped += 1
            continue
        name, address = parts[0], parts[1]
        city = parts[2] if len(parts) > 2 else ""
        phone = parts[3] if len(parts) > 3 else ""
        website = parts[4] if len(parts) > 4 else ""
        kind = parts[5] if len(parts) > 5 and parts[5] else default_type
        kind = "ambassadors" if kind.lower().startswith("amb") else "authorized"

        # Dedup by (name,address)
        db = get_db()
        existing = db.execute("SELECT id FROM clinics WHERE name=? AND address=?", (name, address)).fetchone()
        data = {"kind": kind, "name": name, "address": address, "city": city, "phone": phone, "website": website, "notes": ""}
        if existing:
            upsert_clinic(existing["id"], data, geocode_if_missing=True)
            updated += 1
        else:
            upsert_clinic(None, data, geocode_if_missing=True)
            created += 1
    return created, updated, skipped

# -------------------- Static helpers --------------------
def list_static_images(folder: str):
    base = os.path.join(APP_DIR, "static", folder)
    exts = (".png", ".jpg", ".jpeg", ".webp")
    out = []
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if name.lower().endswith(exts):
                out.append(f"/static/{folder}/{name}")
    return out

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))