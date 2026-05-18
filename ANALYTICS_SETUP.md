# Analytics setup — GTM / GA4 / Google Ads

Ta wersja projektu ma już techniczne podłączenie analityki w kodzie. Nie wpisuj ID na sztywno w HTML — ustaw je jako zmienne środowiskowe na serwerze.

## 1. Wymagane zmienne środowiskowe

Minimalnie ustaw:

```env
GTM_ID=GTM-XXXXXXX
GA4_MEASUREMENT_ID=G-XXXXXXXXXX
```

Opcjonalnie dla konwersji Google Ads:

```env
GOOGLE_ADS_CONVERSION_ID=AW-123456789
GOOGLE_ADS_LEAD_CONVERSION_LABEL=xxxxxxxxxxxx
GOOGLE_ADS_PRESENTATION_CONVERSION_LABEL=yyyyyyyyyyyy
```

## 2. Jak działa wdrożenie

- Jeśli `GTM_ID` jest ustawione, strona ładuje Google Tag Manager w `<head>` oraz `noscript` po `<body>`.
- Jeśli `GTM_ID` nie jest ustawione, ale `GA4_MEASUREMENT_ID` jest ustawione, strona ładuje GA4 bezpośrednio przez `gtag.js`.
- Jeśli ustawione są także dane Google Ads, udane formularze mogą zostać wysłane jako konwersje przy bezpośrednim trybie GA4/gtag.
- Przy pracy przez GTM wszystkie zdarzenia są wysyłane do `dataLayer`, więc w GTM można podpiąć GA4 Event Tags i Google Ads Conversion Tags.
- Dodano Google Consent Mode v2: domyślnie `analytics_storage`, `ad_storage`, `ad_user_data` i `ad_personalization` są ustawione na `denied`, a baner cookies aktualizuje zgody po decyzji użytkownika.

## 3. Zdarzenia wysyłane do `dataLayer`

Podstawowe:

- `analytics_bootstrap`
- `page_ready`
- `cookie_consent_update`
- `form_start`
- `form_submit_attempt`
- `generate_lead`
- `contact_form_submit_success`
- `presentation_request`

Kliknięcia i interakcje:

- `cta_click`
- `phone_click`
- `email_click`
- `social_click`
- `outbound_click`
- `mobile_menu_open`
- `mobile_menu_close`
- `video_sound_toggle`
- `gallery_image_click`
- `gallery_load_more`
- `map_preview_loaded`
- `clinics_map_loaded`
- `map_marker_click`
- `clinic_list_click`

## 4. Konwersje rekomendowane w GA4

Oznacz jako key events / conversions:

- `generate_lead`
- `presentation_request`
- `contact_form_submit_success`
- opcjonalnie: `phone_click`, `email_click`

## 5. Ważne: dane osobowe

Kod nie wysyła do analityki imienia, e-maila, telefonu ani treści wiadomości. Do analityki trafiają tylko techniczne parametry typu `form_name`, `lead_type`, `page_path`, `clinic_id`.

## 6. Test po deployu

1. Otwórz stronę w trybie GTM Preview / Tag Assistant.
2. Sprawdź, czy kontener GTM się ładuje.
3. Wejdź na kilka podstron i sprawdź `page_ready`.
4. Zaakceptuj baner cookies i sprawdź `cookie_consent_update`.
5. Kliknij telefon/e-mail/CTA i sprawdź zdarzenia w `dataLayer`.
6. Wyślij formularz testowy i sprawdź po przekierowaniu `generate_lead` oraz odpowiednie zdarzenie formularza.
7. W GA4 sprawdź DebugView / Realtime.
