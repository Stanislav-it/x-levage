# Google Merchant Center / Produkty sponsorowane — X-Levage

W paczce zostały przygotowane elementy potrzebne do startu kampanii produktowej dla dwóch urządzeń:

- X-Levage Pro — `/laser-tulowy-x-levage-pro`
- X-Levage Erbo — `/x-levage-erbo`

## Co jest już na stronie

Na obu kartach produktu są teraz widoczne i spójne z feedem:

- nazwa produktu,
- opis produktu,
- publiczna cena w PLN,
- status dostępności,
- marka,
- MPN,
- główne zdjęcie produktu,
- kanoniczny URL produktu,
- dane strukturalne Schema.org Product + Offer.

## Feed dla Merchant Center

Po wdrożeniu strony feed będzie dostępny pod adresami:

- `/merchant-feed.xml` — rekomendowany feed XML/RSS dla Google Merchant Center,
- `/product-feed.xml` — alias tego samego feedu,
- `/merchant-feed.tsv` — alternatywny feed tekstowy TSV.

Feed zawiera pola: `id`, `title`, `description`, `link`, `image_link`, `availability`, `price`, `condition`, `brand`, `mpn`, `product_type`, `adult`.

## Dodatkowo dodane

- `/sitemap.xml`
- `/robots.txt`

## Co trzeba zrobić po wdrożeniu

1. Wejść na live domenę i sprawdzić:
   - `/merchant-feed.xml`
   - `/merchant-feed.tsv`
   - `/sitemap.xml`
   - `/robots.txt`
2. W Google Merchant Center potwierdzić i połączyć domenę.
3. Dodać feed przez URL, np. `https://twojadomena.pl/merchant-feed.xml`.
4. Ustawić dostawę i zwroty w Merchant Center zgodnie z realnymi zasadami sprzedaży.
5. Sprawdzić, czy ceny i dostępność na stronie są prawdziwe. Muszą zgadzać się z feedem.
6. Po akceptacji produktów połączyć Merchant Center z Google Ads i uruchomić kampanię produktową / Performance Max.

## Ważna uwaga

Warto zweryfikować finalne treści pod polityki Google dotyczące sprzętu medycznego/kosmetologicznego. W kodzie nie ma gwarancji akceptacji przez Google — decyzję podejmuje moderacja Merchant Center i Google Ads.
