# X‑LEVAGE — Flask site (minimalist)


## Render (коротко по делу — что обязательно включить)
1) **Persistent Disk**: mount path **`/var/data`**.
2) В **Environment** (это список **Key / Value**) выставить минимум:
   - `DATA_DIR` = `/var/data`
   - `SECRET_KEY` = Generate
   - `ADMIN_USER` = ваш логин
   - `ADMIN_PASS` = ваш пароль
3) Где лежат данные на диске:
   - База (все правки из `/admin` + все заявки из формы): **`/var/data/instance/app.db`**
   - Архив заявок файлами (JSON): **`/var/data/leads/`**
   - Архив отправленных писем (EML, опционально): **`/var/data/mail_archive/`**

Если диск не подключен или смонтирован в другой путь, данные не будут сохраняться между деплоями.

## Co jest w środku
- Flask + SQLite (`instance/app.db`)
- Strony:
  - `/` (home)
  - `/laser-tulowy-x-levage-pro`
  - `/x-levage-erbo`
  - `/gabinet` (mapa)
  - `/policies/*` (polityki)
- Panel admin:
  - Logowanie jest konfigurowane przez zmienne środowiskowe (Render Environment Variables).
  - `/admin/login`
  - `/admin` (lista/edycja gabinetów)
  - `/admin/import` (import hurtowy)

## Wymagania
- Python 3.10+

## Instalacja
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Uruchomienie
```bash
flask run
```

### Zmienne środowiskowe
W produkcji ustaw co najmniej:
- `SECRET_KEY` (w Render możesz użyć przycisku **Generate**)
- `ADMIN_USER` i `ADMIN_PASS`

## Materiały (zdjęcia)
Dodaj pliki:
- `static/efekty_zabiegow/*` (przed/po)
- `static/fotos/*` (zdjęcia urządzeń)

Galerie na stronie aktualizują się automatycznie.

## Mapa gabinetów
1. Zaloguj się do panelu (`/admin/login`)
2. Dodaj gabinet (pełny adres: ulica, nr, kod, miasto, kraj)
3. System spróbuje geokodować adres przez Nominatim.
4. Jeżeli współrzędne są puste — użyj przycisku **Geokoduj**.

Uwaga: Nominatim ma limity. Importuj w partiach.

## Deploy
### Render.com (rekomendowane)
Render uruchamia aplikację jako **Web Service** na runtime **Python 3** i startuje ją przez Gunicorn.

**1) Create Web Service**
- Language/Runtime: **Python 3**
- Build Command:
  ```bash
  pip install -r requirements.txt
  ```
- Start Command:
  ```bash
  gunicorn app:app
  ```

**2) Persistent Disk (SQLite + dane z panelu admin)**
Jeśli chcesz, żeby dane (SQLite) przetrwały deploy/restart, dodaj **Persistent Disk** i ustaw mount path (np. `/var/data`).

W Render -> Twoj serwis -> **Disks**:
- Add disk
- Mount path: `/var/data`

Następnie w Render -> **Environment** (to jest lista **Key / Value**) dodaj:
- `DATA_DIR` = `/var/data`

**3) Environment Variables (minimum)**
- `SECRET_KEY` = (Generate)
- `ADMIN_USER` = (np. twoj_login)
- `ADMIN_PASS` = (mocne haslo)
- `CONTACT_EMAIL` = `xlevage@gmail.com` (pokazywany w stopce)
- `INSTAGRAM_HANDLE` = `xestetik`
- `INSTAGRAM_URL` = `https://www.instagram.com/xestetik?utm_source=ig_web_button_share_sheet&igsh=ZDNlZDc0MzIxNw==`
- `NOMINATIM_USER_AGENT` = `xlevage-site/1.0 (contact: xlevage@gmail.com)`

**4) Powiadomienia e‑mail z formularza (opcjonalne, SMTP)**
Jeżeli chcesz, aby zgłoszenia z formularza przychodziły na e‑mail, skonfiguruj SMTP.

Minimalnie ustaw:
- `MAIL_TO` = `xlevage@gmail.com`
- `SMTP_HOST` = `smtp.gmail.com`
- `SMTP_PORT` = `587`
- `SMTP_TLS` = `1`
- `SMTP_USER` = (np. `xlevage@gmail.com`)
- `SMTP_PASS` = (dla Gmail: **App Password**, nie zwykłe hasło)
- `SMTP_FROM` = `xlevage@gmail.com` (lub zostaw puste, wtedy użyje `SMTP_USER`)

Jeżeli hostujesz pod domeną, zadbaj o HTTPS (Render daje HTTPS automatycznie dla domeny *.onrender.com).

**Dodatkowo (opcjonalne archiwum na dysku):**
- `LEADS_DIR` = `/var/data/leads` (jeśli puste, domyślnie i tak zapisuje pod DATA_DIR)
- `MAIL_ARCHIVE_DIR` = `/var/data/mail_archive` (zapisuje kopię wysłanego e‑maila jako plik `.eml`)
