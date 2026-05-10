# Deployment-Checkliste: Hetzner Production

## 1. Hetzner VPS anlegen

- [X] **VPS bestellen**

  - Hetzner Cloud Console öffnen: [console.hetzner.cloud](https://console.hetzner.cloud)
  - Typ: **CX22** (2 vCPU, 4 GB RAM) — ausreichend für Single-User, bei Bedarf auf CX32 upgraden
  - Image: **Ubuntu 24.04 LTS**
  - Rechenzentrum: **Nürnberg oder Falkenstein** (Deutschland, DSGVO)
  - SSH-Key hinterlegen (bestehenden Key nutzen oder neuen erstellen)
  - Hostname vergeben, z.B. `liquisto-runtime`
- [X] **Firewall konfigurieren**

  - In Hetzner Cloud: Firewall-Regel anlegen
  - Eingehend erlauben: Port 22 (SSH), Port 80 (HTTP), Port 443 (HTTPS)
  - Alle anderen eingehenden Ports sperren
  - Firewall dem VPS zuweisen
- [X] **Ersten Login testen**

  ```bash
  ssh root@<SERVER-IP>
  ```

---

## 2. Server-Grundkonfiguration

- [X] **System aktualisieren**

  ```bash
  apt update && apt upgrade -y
  ```
- [ ] **Nicht-root-User anlegen** (optional, aber empfohlen)

  ```bash
  adduser liquisto
  usermod -aG sudo liquisto
  ```
- [X] **Docker installieren**

  ```bash
  curl -fsSL https://get.docker.com | sh
  ```

  Danach prüfen:

  ```bash
  docker --version
  ```
- [X] **Docker Compose installieren**

  ```bash
  apt install docker-compose-plugin -y
  ```

  Prüfen:

  ```bash
  docker compose version
  ```

---

## 3. GitHub Actions Deploy-Workflow

- [X] **SSH Deploy-Key erzeugen**
  Auf dem Server:

  ```bash
  ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/github_deploy
  cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys
  cat ~/.ssh/github_deploy  # Privaten Key kopieren
  ```
- [X] **GitHub Secrets hinterlegen**
  Im GitHub-Repo unter *Settings → Secrets and variables → Actions*:

  - `HETZNER_HOST` — IP-Adresse des VPS
  - `HETZNER_USER` — `root` oder der angelegte User
  - `HETZNER_SSH_KEY` — privater SSH-Key (Inhalt von `github_deploy`)
  - `OPENAI_API_KEY` — bereits vorhanden ✓
- [X] **`docker-compose.yml` im Repo anlegen**
  Datei: `docker-compose.yml` im Projektroot

  ```yaml
  services:
    app:
      image: ghcr.io/<ORG>/<REPO>:latest
      restart: unless-stopped
      ports:
        - "8501:8501"
      environment:
        - OPENAI_API_KEY=${OPENAI_API_KEY}
      volumes:
        - artifacts:/app/artifacts
  volumes:
    artifacts:
  ```
- [X] **GitHub Actions Workflow anlegen**
  Datei: `.github/workflows/deploy.yml`

  ```yaml
  name: Deploy to Hetzner

  on:
    push:
      branches: [main]

  jobs:
    deploy:
      runs-on: ubuntu-latest
      steps:
        - name: Deploy via SSH
          uses: appleboy/ssh-action@v1
          with:
            host: ${{ secrets.HETZNER_HOST }}
            username: ${{ secrets.HETZNER_USER }}
            key: ${{ secrets.HETZNER_SSH_KEY }}
            script: |
              cd /opt/liquisto
              docker compose pull
              OPENAI_API_KEY=${{ secrets.OPENAI_API_KEY }} docker compose up -d
  ```
- [X] **Projektverzeichnis auf Server anlegen**

  ```bash
  mkdir -p /opt/liquisto
  # docker-compose.yml manuell oder per scp übertragen
  ```
- [ ] **Ersten Deploy manuell auslösen und Logs prüfen**

  ```bash
  docker compose logs -f
  ```

---

## 4. HTTPS mit Nginx + Certbot

- [X] **Domain auf Server-IP zeigen lassen**

  - DNS A-Record anlegen: `app.deinedomain.de` → `<SERVER-IP>`
  - Propagation abwarten (5–30 Min)
- [X] **Nginx installieren**

  ```bash
  apt install nginx -y
  ```
- [X] **Nginx-Konfiguration anlegen**
  Datei: `/etc/nginx/sites-available/liquisto`

  ```nginx
  server {
      listen 80;
      server_name app.deinedomain.de;

      location / {
          proxy_pass http://localhost:8501;
          proxy_http_version 1.1;
          proxy_set_header Upgrade $http_upgrade;
          proxy_set_header Connection "upgrade";
          proxy_set_header Host $host;
          proxy_read_timeout 3600;
      }
  }
  ```

  Aktivieren:

  ```bash
  ln -s /etc/nginx/sites-available/liquisto /etc/nginx/sites-enabled/
  nginx -t && systemctl reload nginx
  ```
- [ ] **SSL-Zertifikat mit Certbot ausstellen**

  ```bash
  apt install certbot python3-certbot-nginx -y
  certbot --nginx -d app.deinedomain.de
  ```

  Certbot konfiguriert Nginx automatisch für HTTPS und richtet Auto-Renewal ein.
- [ ] **HTTPS im Browser testen**
  `https://app.deinedomain.de` aufrufen — Streamlit-UI muss erscheinen.

---

## 5. Zugriffsschutz

- [ ] **Zugriffsschutz-Methode wählen** (eine der folgenden):

  **Option A — Cloudflare Access (empfohlen)**

  - Domain zu Cloudflare hinzufügen (kostenlos)
  - Zero Trust → Access → Application anlegen
  - Zugelassene E-Mail-Adressen des Kunden eintragen
  - Kein Login-System nötig, Zugang per E-Mail-OTP

  **Option B — HTTP Basic Auth via Nginx**

  ```bash
  apt install apache2-utils -y
  htpasswd -c /etc/nginx/.htpasswd <benutzername>
  ```

  In der Nginx-Config ergänzen:

  ```nginx
  auth_basic "Restricted";
  auth_basic_user_file /etc/nginx/.htpasswd;
  ```
- [ ] **Zugriffsschutz testen**
  Inkognito-Fenster öffnen und URL aufrufen — Login-Prompt muss erscheinen.

---

## 6. Backup-Strategie

- [ ] **Hetzner Volume anlegen** (optional, für persistente Artifacts)

  - In Hetzner Cloud: Volume anlegen (10–20 GB), am VPS mounten
  - Docker Volume auf das Hetzner Volume umlenken
- [ ] **Automatische Hetzner Snapshots aktivieren**

  - In Hetzner Cloud: VPS auswählen → *Backups* → aktivieren
  - Kostet ca. 20% des VPS-Preises (~1€/Monat)
  - Täglicher Snapshot, 7 Versionen aufbewahrt
- [ ] **Backup-Restore einmal testen**
  Snapshot wiederherstellen oder Volume-Inhalt manuell sichern und zurückspielen.

---

## 7. Monitoring & Wartung

- [ ] **Container-Restart-Policy prüfen**
  In `docker-compose.yml`: `restart: unless-stopped` sicherstellt automatischen Neustart nach Serverreboot.
- [ ] **Uptime-Monitor einrichten** (optional)

  - [UptimeRobot](https://uptimerobot.com) (kostenlos, 5-Min-Intervall)
  - URL des Deployments eintragen → E-Mail-Alert bei Ausfall
- [ ] **Log-Rotation konfigurieren**
  In `docker-compose.yml` unter dem Service:

  ```yaml
  logging:
    driver: "json-file"
    options:
      max-size: "50m"
      max-file: "5"
  ```
- [ ] **Update-Prozess dokumentieren**
  Neues Release wird automatisch deployed, sobald ein Push auf `main` erfolgt (GitHub Actions Workflow aus Schritt 3).

---

## 8. Abnahme & Übergabe

- [ ] **End-to-End-Test durchführen**

  - Über die Produktions-URL einloggen
  - Einen vollständigen Pipeline-Run mit einem Testunternehmen durchführen
  - PDF-Export prüfen
  - Artifacts auf dem Server prüfen: `docker exec <container> ls /app/artifacts/runs/`
- [ ] **Zugangsdaten an Kunden übergeben**

  - URL des Deployments
  - Login-Credentials (Cloudflare Access E-Mail oder Basic Auth Passwort)
- [ ] **AVV mit Hetzner abschließen**

  - Hetzner Kundencenter → *Rechtliches* → Auftragsverarbeitungsvertrag herunterladen und unterzeichnen
  - Für DSGVO-konformen Betrieb erforderlich
- [ ] **AVV mit Kunden abschließen** (falls ihr die Infrastruktur betreibt)

  - Ihr verarbeitet ggf. personenbezogene Daten (Kontaktdaten aus Contact-Department) im Auftrag des Kunden
