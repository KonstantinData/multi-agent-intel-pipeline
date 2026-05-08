# Server Setup: Hetzner CX23

Step-by-step guide for provisioning and configuring the production server on Hetzner Cloud.

---

## 1. Create the Server (Hetzner Cloud Console)

1. Open [console.hetzner.cloud](https://console.hetzner.cloud) and log in
2. Select or create a project
3. Click **Create Server** and choose the following options:

| Setting | Value |
|---|---|
| Type | Cost-Optimized x86 · **CX23** |
| Image | **Ubuntu 24.04 LTS** |
| Data center | **Nuremberg** (Germany, GDPR-compliant) |
| Networking | IPv4 + IPv6 |
| SSH Key | Use existing key or create a new one |
| Backups | **Enable** (~20% of server price/month) |
| Volume | Not required |
| Placement group | None |
| Cloud config | None |
| Server name | `liquisto-runtime` |

### Check or create an SSH key

Display an existing key (local PowerShell):
```powershell
Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub"
```

If no key exists yet:
```powershell
ssh-keygen -t ed25519 -C "hetzner-liquisto"
```

Paste the contents of the `.pub` file into Hetzner under **SSH Keys** and mark it as default.

---

## 2. Configure the Firewall

In the Hetzner Console under **Firewalls**, create a new firewall named `liquisto-firewall`.

### Inbound rules

| Protocol | Port | Source |
|---|---|---|
| ICMP | — | Any IPv4 + Any IPv6 |
| TCP | 22 | Any IPv4 + Any IPv6 |
| TCP | 80 | Any IPv4 + Any IPv6 |
| TCP | 443 | Any IPv4 + Any IPv6 |

**Outbound:** Leave as default (all traffic allowed).

Assign the firewall to the `liquisto-runtime` server.

> Port 8501 (Streamlit) is intentionally closed. Streamlit only listens on localhost and is exposed externally through Nginx.

---

## 3. First Login

```powershell
ssh root@<SERVER-IP>
```

Confirm the host authenticity on first connection:
```
Are you sure you want to continue connecting (yes/no/[fingerprint])? yes
```

---

## 4. Update the System

```bash
apt update && apt upgrade -y
```

After the upgrade completes, check whether a kernel update was applied. If you see a message indicating the running kernel does not match the expected version:

```bash
reboot
```

Wait ~30 seconds, then log back in:

```powershell
ssh root@<SERVER-IP>
```

---

## 5. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
```

Verify the installation:
```bash
docker --version
```

Install the Docker Compose plugin (may already be installed as a dependency):
```bash
apt install docker-compose-plugin -y
```

Verify Compose:
```bash
docker compose version
```

---

## 6. Create SSH Deploy Key for GitHub Actions

Generate a dedicated ED25519 key pair on the server for GitHub Actions:

```bash
ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/github_deploy
```

Leave the passphrase empty (press Enter twice).

Add the public key to `authorized_keys`:
```bash
cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys
```

Display the private key (needed for GitHub Secrets):
```bash
cat ~/.ssh/github_deploy
```

Copy the entire output from `-----BEGIN OPENSSH PRIVATE KEY-----` to `-----END OPENSSH PRIVATE KEY-----` (inclusive).

---

## 7. Add GitHub Secrets

In the GitHub repository under **Settings → Secrets and variables → Actions**, add the following secrets:

| Secret Name | Description |
|---|---|
| `HETZNER_HOST` | Server IP address |
| `HETZNER_USER` | `root` |
| `HETZNER_SSH_KEY` | Full private key content including header and footer lines |
| `OPENAI_API_KEY` | OpenAI API key (already present) |

---

## 8. Create Project Directory on the Server

On the server:
```bash
mkdir -p /opt/liquisto
```

Copy `docker-compose.yml` from your local machine to the server (local PowerShell):
```powershell
scp "docker-compose.yml" root@<SERVER-IP>:/opt/liquisto/
```

---

## 9. GitHub Actions Deploy Workflow

The file `.github/workflows/deploy.yml` triggers an automatic deployment whenever the `Release Attestation` workflow completes successfully on `main`.

**Deployment flow:**

1. Push to `main`
2. `Release Attestation` builds the Docker image and pushes it to GHCR
3. `Deploy to Hetzner` connects via SSH to the server
4. `docker compose pull` downloads the new image
5. `docker compose up -d` restarts the container
6. `docker image prune -f` removes outdated images

---

## 10. Next Steps

After completing this setup, continue with:

- [ ] Set up HTTPS with Nginx + Certbot → [DEPLOYMENT_CHECKLIST.md](../DEPLOYMENT_CHECKLIST.md) Step 4
- [ ] Configure access protection (Cloudflare Access or HTTP Basic Auth) → Step 5
- [ ] Set up uptime monitoring → Step 7
- [ ] Run end-to-end test → Step 8
