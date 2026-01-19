
import os
import sqlite3
import time
from datetime import datetime
from email.message import EmailMessage
import smtplib
from urllib.parse import urlencode

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

def _first_writable_dir(candidates: list[str]) -> str:
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


def resolve_storage_paths() -> tuple[str, str]:
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

    def archive_lead_to_disk(*, lead_id: int, created_at: str, name: str, email: str, phone: str, message: str) -> None:
        """Persist the lead as a JSON file on disk (optional).

        This is useful on Render when you want a simple file-level archive in addition to SQLite.
        It is best-effort and must never break the user flow.
        """
        leads_dir = (app.config.get('LEADS_DIR') or '').strip()
        if not leads_dir:
            return
        try:
            os.makedirs(leads_dir, exist_ok=True)
            safe_ts = created_at.replace(':', '').replace('-', '').replace('T', '_')
            fn = f"lead_{lead_id}_{safe_ts}.json"
            path = os.path.join(leads_dir, fn)
            import json
            payload = {
                'id': int(lead_id),
                'created_at_utc': created_at,
                'name': name,
                'email': email,
                'phone': phone,
                'message': message,
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(f"[WARN] Failed to archive lead to disk: {exc}")

    def send_lead_email(*, name: str, email: str, phone: str, message: str, lead_id: int | None = None, created_at: str | None = None) -> bool:
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
        view = request.args.get("view", "ambassadors")  # ambassadors | authorized | all
        q = request.args.get("q", "").strip()
        clinics = search_clinics(view=view, q=q, limit=500)
        return render_template("gabinet.html", clinics=clinics, view=view, q=q)

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
            "is_admin": is_admin(),
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

    # Seed initial demo clinics (Poland) so the map works out-of-the-box.
    seed_demo_clinics(db)


def seed_demo_clinics(db):
    try:
        cnt = db.execute("SELECT COUNT(1) AS c FROM clinics").fetchone()["c"]
    except Exception:
        return
    if cnt and int(cnt) > 0:
        return

    now = datetime.utcnow().isoformat(timespec="seconds")
    demo = [
        ("ambassadors", "X‑Levage Studio Warszawa", "ul. Marszałkowska 99, 00-693 Warszawa", "Warszawa", "+48 500 111 222", "https://example.com", "", 52.2297, 21.0122),
        ("authorized", "Klinika Estetyczna Kraków", "ul. Floriańska 44, 31-021 Kraków", "Kraków", "+48 500 222 333", "https://example.com", "", 50.0614, 19.9366),
        ("authorized", "Centrum Laserowe Wrocław", "ul. Świdnicka 12, 50-068 Wrocław", "Wrocław", "+48 500 333 444", "https://example.com", "", 51.1079, 17.0385),
        ("ambassadors", "Gabinet Premium Poznań", "ul. Półwiejska 2, 61-888 Poznań", "Poznań", "+48 500 444 555", "https://example.com", "", 52.4064, 16.9252),
        ("authorized", "X‑Levage Gdańsk", "ul. Długa 10, 80-827 Gdańsk", "Gdańsk", "+48 500 555 666", "https://example.com", "", 54.3520, 18.6466),
        ("authorized", "Dermalab Katowice", "ul. Mariacka 26, 40-014 Katowice", "Katowice", "+48 500 666 777", "https://example.com", "", 50.2649, 19.0238),
        ("ambassadors", "Instytut Urody Lublin", "ul. Krakowskie Przedmieście 15, 20-002 Lublin", "Lublin", "+48 500 777 888", "https://example.com", "", 51.2465, 22.5684),
        ("authorized", "Clinic Szczecin", "al. Wyzwolenia 23, 70-531 Szczecin", "Szczecin", "+48 500 888 999", "https://example.com", "", 53.4285, 14.5528),
    ]
    for kind, name, address, city, phone, website, notes, lat, lon in demo:
        db.execute(
            """INSERT INTO clinics(kind,name,address,city,phone,website,notes,lat,lon,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (kind, name, address, city, phone, website, notes, lat, lon, now, now),
        )
    db.commit()

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
    if view in ("ambassadors", "authorized"):
        where.append("kind=?")
        params.append(view)
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

    db = get_db()
    cached = db.execute("SELECT lat, lon FROM geocode_cache WHERE address=?", (address,)).fetchone()
    if cached and cached["lat"] and cached["lon"]:
        return (cached["lat"], cached["lon"])

    # Polite Nominatim usage: one request per second and a valid UA.
    time.sleep(1.0)
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"format": "json", "limit": 1, "q": address},
            headers={"User-Agent": os.environ.get("NOMINATIM_USER_AGENT", "xlevage-site/1.0")},
            timeout=10,
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
