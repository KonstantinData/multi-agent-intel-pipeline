# Secrets-Management

Dieses Dokument beschreibt die verbindliche Behandlung von API-Keys und anderen
Runtime-Secrets im Liquisto Department Runtime Repository.

Die kanonische Implementierung liegt in:

- `src/config/settings.py`
- `preflight.py`
- `tests/smoke/test_preflight.py`

## Ziel

Secrets duerfen nicht versehentlich aus lokalen Dateien, Logs, Testausgaben oder
Commits offengelegt werden. API-Keys werden deshalb ueber eine feste
Prioritaetskette aufgeloest. Eine Plaintext `.env`-Datei ist keine zulaessige
Quelle fuer API-Keys.

## API-Key-Prioritaet

Die OpenAI API-Key-Aufloesung erfolgt in `src/config/settings.py` ueber
`resolve_openai_api_key()`.

Die Reihenfolge ist strikt:

1. Prozess-Umgebungsvariable oder Deployment-Secret
2. OS-Keyring ueber `python-keyring`

Sobald eine Quelle einen nicht-leeren Wert liefert, wird diese Quelle verwendet.
Nachrangige Quellen werden dann nicht mehr fuer den API-Key verwendet.

## Prozess- und Deployment-Secrets

Die bevorzugte Quelle ist die Prozess-Umgebungsvariable:

```powershell
$env:OPENAI_API_KEY = "<secret value>"
```

In Deployment- und CI-Umgebungen soll `OPENAI_API_KEY` als Plattform-Secret
gesetzt und zur Laufzeit als Environment Variable injiziert werden. Das Secret
wird nicht in Repository-Dateien, Build-Artefakte oder Logs geschrieben.

Diese Quelle hat Vorrang vor dem OS-Keyring.

## OS-Keyring

Fuer lokale Entwicklung ist der OS-Keyring die empfohlene persistente
Secret-Quelle. Der Key wird mit `python-keyring` gespeichert:

```powershell
python -m keyring set liquisto-department-runtime OPENAI_API_KEY
```

Dabei ist:

- `liquisto-department-runtime` der Keyring-Service
- `OPENAI_API_KEY` der Keyring-Account

Die Anwendung liest den Wert ueber `keyring.get_password(...)`. Der tatsaechliche
Secret-Wert darf nie ausgegeben, geloggt oder in Test-Fixtures festgeschrieben
werden.

Optional koennen Service und Account fuer spezielle lokale Umgebungen angepasst
werden:

```powershell
$env:LIQUISTO_KEYRING_SERVICE = "custom-service"
$env:OPENAI_API_KEY_KEYRING_ACCOUNT = "custom-account" # pragma: allowlist secret
```

Diese Overrides sind Konfiguration, keine Secrets. Sie duerfen keinen
Secret-Wert enthalten.

## Keine `.env` fuer API-Keys

`OPENAI_API_KEY` wird nicht aus `.env` gelesen.

Das gilt auch dann, wenn eine lokale `.env`-Datei existiert oder ein alter
Freigabe-Schalter wie `LIQUISTO_ALLOW_DOTENV_SECRETS` gesetzt ist. Dieser
Schalter ist fuer die API-Key-Aufloesung nicht mehr wirksam.

Die Datei `.env` ist in `.gitignore` eingetragen und soll nicht committed
werden. Im Standardbetrieb ist keine `.env`-Datei erforderlich.

## Nicht geheime Konfiguration

Einige nicht geheimen Runtime-Optionen koennen weiterhin ueber Environment oder
lokale `.env` gelesen werden, zum Beispiel Modellnamen oder Timeout-Werte.
Das betrifft nicht die API-Key-Regel. Fuer `OPENAI_API_KEY` gelten nur
Prozess-/Deployment-Secret und OS-Keyring.

Beispiele fuer nicht geheime Konfiguration:

- `OPENAI_MODEL`
- `OPENAI_MODEL_SEARCH`
- `OPENAI_MODEL_TRANSLATION`
- `OPENAI_MODEL_EXTRACTION`
- `LIQUISTO_OPENAI_TIMEOUT_SECONDS`
- `LIQUISTO_OPENAI_MAX_RETRIES`

## Preflight-Verhalten

`preflight.py` prueft, ob ein Model API Credential verfuegbar ist. Die Ausgabe
darf nur einen bereinigten Status enthalten.

Erlaubte Ausgabe:

```text
Model API credential: configured
```

Nicht erlaubt:

- Ausgabe des API-Key-Werts
- Ausgabe des Secret-Namens als Log-Label
- Ausgabe der Keyring-Quelle inklusive Account
- Ausgabe von `.env`-Inhalten
- Ausgabe ganzer Environment-Variablen

Der Preflight-Check darf intern `resolve_openai_api_key()` verwenden, muss die
zurueckgegebenen Detailinformationen aber fuer die Konsolenausgabe verwerfen.

## Logging-Regeln

Secrets duerfen nicht in Logs erscheinen. Das gilt fuer:

- API-Keys
- Environment-Werte
- Keyring-Inhalte
- Auth-Header
- Cookies
- komplette `.env`-Dateien

Zulaessig sind ausschliesslich boolesche oder bereinigte Statusmeldungen, zum
Beispiel `configured`, `missing` oder `api_key_present: true`.

## Commit- und CI-Schutz

Die Datei `.env` ist per `.gitignore` ausgeschlossen.

Zusaetzlich enthaelt die CI zwei Secret-Gates:

- `detect-secrets` scannt den aktuellen Arbeitsbaum.
- Gitleaks scannt die Repository-Historie mit `.gitleaks.toml`.

Beide Reports werden durch `scripts/validate_secret_scan.py` ausgewertet und
blockieren den Workflow bei Findings. Diese Scans ersetzen nicht die lokale
Sorgfalt: Secrets duerfen gar nicht erst in Arbeitskopie, Tests,
Debug-Ausgaben oder Dokumentationsbeispiele geschrieben werden.

GitHub Secret Scanning und Push Protection sind verpflichtende
Repository-Settings. Sie muessen durch einen Repository-Admin aktiviert bleiben,
damit Secrets schon vor dem Push blockiert werden.

## Testabdeckung

Die Smoke-Tests in `tests/smoke/test_preflight.py` pruefen:

- leere API-Key-Werte werden abgelehnt
- `.env` wird fuer API-Keys ignoriert, auch wenn ein Legacy-Schalter gesetzt ist
- Prozess-Environment hat Vorrang
- OS-Keyring wird verwendet, wenn kein Prozess-Secret gesetzt ist
- Preflight gibt nur einen bereinigten Credential-Status aus

Der relevante Testlauf ist:

```powershell
pytest tests/smoke/test_preflight.py -q
```

## Lokale Einrichtung

Empfohlener lokaler Weg:

```powershell
python -m keyring set liquisto-department-runtime OPENAI_API_KEY
python preflight.py
```

`preflight.py` soll anschliessend nur melden, dass ein Model API Credential
konfiguriert ist. Es soll keinen API-Key-Wert und keine konkrete Secret-Quelle
anzeigen.

## Fehlerbehebung

Wenn Preflight kein Credential findet:

1. Pruefen, ob der Key im OS-Keyring gesetzt wurde.
2. Pruefen, ob die virtuelle Umgebung `keyring` installiert hat.
3. Pruefen, ob ein Deployment-Secret als Prozess-Environment injiziert wird.
4. Keine `.env` als API-Key-Fallback verwenden.

Wenn ein Secret versehentlich geloggt oder committed wurde:

1. Den betroffenen API-Key sofort rotieren.
2. Den Log- oder Commit-Pfad bereinigen.
3. Den GitHub Secret-Scanning-Alert schliessen oder dokumentiert remediieren.
4. Tests fuer bereinigte Ausgabe ergaenzen oder verschaerfen.
5. Preflight, `detect-secrets` und Gitleaks erneut ausfuehren.
