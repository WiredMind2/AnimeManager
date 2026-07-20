# Cloudflare Tunnel + Access setup (tetrazero)

AnimeManager public URLs:

| Hostname | Caddy upstream | Purpose |
|----------|----------------|---------|
| `anime.tetrazero.com` | `localhost:3010` | Web UI |
| `observability.tetrazero.com` | `localhost:5601` | Kibana |

Local routing is configured in TetrazeroDashboard `services.yaml` + Caddy `:9080`.

## 1. Tunnel public hostnames (required — fixes external 502)

The running tunnel (`tetrazero`, ID `aeade0d6-e7af-4a0d-89cf-3c7f9b46d59b`) is **remotely managed** (systemd uses `--token`). Ingress rules live in the Cloudflare dashboard, not in local `config.yml`.

**Zero Trust → Networks → Tunnels → tetrazero → Configure → Public Hostname**

Update or add:

| Public hostname | Service type | URL |
|-----------------|--------------|-----|
| `anime.tetrazero.com` | HTTP | `http://localhost:9080` |
| `observability.tetrazero.com` | HTTP | `http://localhost:9080` |

Using `:9080` (Caddy) keeps all vhosts consistent. Caddy routes by `Host` header to `3010` / `5601`.

**Alternative (direct, like `bobst.tetrazero.com`):**

| Hostname | URL |
|----------|-----|
| `anime.tetrazero.com` | `http://localhost:3010` |
| `observability.tetrazero.com` | `http://localhost:5601` |

Remove any stale rule pointing `anime.tetrazero.com` → `http://127.0.0.1:8001`.

DNS for `observability.tetrazero.com` was added via:

```bash
cloudflared tunnel route dns aeade0d6-e7af-4a0d-89cf-3c7f9b46d59b observability.tetrazero.com
```

## 2. Cloudflare Access (auth gate)

**Zero Trust → Access → Applications → Add an application → Self-hosted**

Create two apps:

| App name | Domain | Session |
|----------|--------|---------|
| AnimeManager | `anime.tetrazero.com` | 24h |
| AnimeManager Observability | `observability.tetrazero.com` | 24h |

For each app, add an **Allow** policy (e.g. emails ending in `@yourdomain.com`, or one-time PIN, or Google/GitHub).

Unauthenticated requests should return **302** to `*.cloudflareaccess.com`.

## 3. API automation (optional)

If you have a Cloudflare API token with **Account → Cloudflare Tunnel Edit**, **Access: Apps and Policies Edit**, and **Zone → DNS Edit**:

```bash
export CLOUDFLARE_API_TOKEN=...
./docker/setup-cloudflare-tunnel.sh
```

Account ID: `04b24ad5413da4511d033291ca96d634`  
Tunnel ID: `aeade0d6-e7af-4a0d-89cf-3c7f9b46d59b`

## 4. Verify

```bash
# On tetrazero (Caddy)
curl -I -H 'Host: anime.tetrazero.com' http://127.0.0.1:9080/
curl -I -H 'Host: observability.tetrazero.com' http://127.0.0.1:9080/

# External (logged out → Access redirect; logged in → 200/307)
curl -I https://anime.tetrazero.com/library
curl -I https://observability.tetrazero.com
```

## 5. AnimeManager env

```env
APP_URL=https://anime.tetrazero.com
WEB_PORT=3010
```

Kibana public URL lives in **tetrazero-observability** `.env`:

```env
KIBANA_PUBLIC_URL=https://observability.tetrazero.com
```

Rebuild after changing `APP_URL`:

```bash
docker compose up -d --build web backend
cd ../tetrazero-observability && docker compose up -d kibana
```
