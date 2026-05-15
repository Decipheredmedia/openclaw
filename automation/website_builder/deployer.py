"""
website_builder/deployer.py — Deploys a generated site to Nginx with SSL.

For each configured domain the deployer:
  1. Writes an Nginx server block pointing to the generated site root.
  2. Runs nginx -t to validate the configuration.
  3. Obtains an SSL certificate via certbot --webroot.
  4. Reloads Nginx.
  5. Validates the site is live (HTTP 200) by hitting the domain.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

BUILDER_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BUILDER_DIR / "generated"
NGINX_SITES_AVAILABLE = Path("/etc/nginx/sites-available")
NGINX_SITES_ENABLED = Path("/etc/nginx/sites-enabled")


def _run(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    log.info("$ %s", cmd)
    return subprocess.run(cmd, shell=True, text=True, capture_output=True, check=check)


def _nginx_conf_name(domain: str) -> str:
    return f"{domain}.conf"


def write_nginx_config(domain: str, site_root: Path, cfg) -> Path:
    """
    Write /etc/nginx/sites-available/<domain>.conf for the generated static site.
    Includes:
      - HTTP → HTTPS redirect
      - Static file serving
      - Proxy pass for /api/ → the FastAPI payment server
      - Basic security headers
    """
    payment_port = cfg.PAYMENT_SERVER_PORT
    conf = textwrap.dedent(f"""\
        # {domain} — managed by openclaw-automation deployer
        # DO NOT EDIT MANUALLY

        server {{
            listen 80;
            listen [::]:80;
            server_name {domain} www.{domain};

            # Let's Encrypt webroot challenge
            location ^~ /.well-known/acme-challenge/ {{
                root {cfg.CERTBOT_WEBROOT};
                default_type text/plain;
            }}

            location / {{
                return 301 https://$host$request_uri;
            }}
        }}

        server {{
            listen 443 ssl http2;
            listen [::]:443 ssl http2;
            server_name {domain} www.{domain};

            ssl_certificate     /etc/letsencrypt/live/{domain}/fullchain.pem;
            ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
            include             /etc/letsencrypt/options-ssl-nginx.conf;
            ssl_dhparam         /etc/letsencrypt/ssl-dhparams.pem;

            root {site_root};
            index index.html;

            # Security headers
            add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
            add_header X-Content-Type-Options nosniff always;
            add_header X-Frame-Options SAMEORIGIN always;
            add_header Referrer-Policy strict-origin-when-cross-origin always;

            # Static assets — long cache
            location ~* \\.(ico|css|js|gif|png|jpg|jpeg|svg|woff2?)$ {{
                expires 1y;
                add_header Cache-Control "public, immutable";
            }}

            # API proxy → FastAPI payment/contact server
            location /api/ {{
                proxy_pass http://127.0.0.1:{payment_port}/;
                proxy_set_header Host $host;
                proxy_set_header X-Real-IP $remote_addr;
                proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                proxy_set_header X-Forwarded-Proto https;
                proxy_read_timeout 30s;
            }}

            # Webhook endpoints (Stripe, PayPal)
            location /webhook/ {{
                proxy_pass http://127.0.0.1:{payment_port}/webhook/;
                proxy_set_header Host $host;
                proxy_set_header X-Real-IP $remote_addr;
                proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                proxy_set_header X-Forwarded-Proto https;
                proxy_read_timeout 30s;
            }}

            # SPA fallback — serve index.html for unknown routes
            location / {{
                try_files $uri $uri/ /index.html;
            }}
        }}
    """)

    NGINX_SITES_AVAILABLE.mkdir(parents=True, exist_ok=True)
    conf_path = NGINX_SITES_AVAILABLE / _nginx_conf_name(domain)
    conf_path.write_text(conf)
    log.info("Written Nginx config: %s", conf_path)

    # Enable the site (symlink)
    NGINX_SITES_ENABLED.mkdir(parents=True, exist_ok=True)
    link = NGINX_SITES_ENABLED / _nginx_conf_name(domain)
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(conf_path)
    log.info("Enabled: %s → %s", link, conf_path)

    return conf_path


def test_nginx_config() -> bool:
    """Run nginx -t and return True if the config is valid."""
    result = _run("nginx -t", check=False)
    if result.returncode == 0:
        log.info("Nginx config test passed.")
        return True
    log.error("Nginx config test FAILED:\n%s\n%s", result.stdout, result.stderr)
    return False


def reload_nginx() -> None:
    _run("systemctl reload nginx")
    log.info("Nginx reloaded.")


def obtain_ssl_certificate(domain: str, email: str, webroot: str) -> bool:
    """
    Attempt to obtain (or renew) a Let's Encrypt certificate for *domain*.
    Returns True on success.
    """
    Path(webroot).mkdir(parents=True, exist_ok=True)
    cmd = (
        f"certbot certonly --webroot -w {webroot} -d {domain} -d www.{domain} "
        f"--non-interactive --agree-tos -m {email} --keep-until-expiring"
    )
    result = _run(cmd, check=False)
    if result.returncode == 0:
        log.info("SSL certificate obtained/renewed for %s.", domain)
        return True
    log.warning(
        "Certbot failed for %s (returncode=%d):\n%s",
        domain, result.returncode, result.stderr,
    )
    return False


def validate_site(domain: str, retries: int = 5, delay: int = 5) -> bool:
    """
    Hit https://<domain>/ and confirm it returns HTTP 200.
    Retries a few times to allow Nginx to reload.
    """
    url = f"https://{domain}/"
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                if resp.status == 200:
                    log.info("✓ Site %s is live (HTTP %d).", domain, resp.status)
                    return True
                log.warning("Attempt %d: %s returned HTTP %d.", attempt, url, resp.status)
        except urllib.error.HTTPError as exc:
            log.warning("Attempt %d: HTTP error %d for %s.", attempt, exc.code, url)
        except Exception as exc:
            log.warning("Attempt %d: %s → %s", attempt, url, exc)
        if attempt < retries:
            time.sleep(delay)

    log.error("Site %s did not return HTTP 200 after %d attempts.", domain, retries)
    return False


def deploy_site(domain: str) -> bool:
    """
    Full deployment pipeline for a single domain:
      write Nginx config → test config → obtain SSL → reload Nginx → validate.

    Returns True if the site is confirmed live.
    """
    sys.path.insert(0, str(BUILDER_DIR.parent))
    from config import cfg  # noqa: PLC0415

    site_root = GENERATED_DIR / domain
    if not site_root.exists():
        log.error(
            "Generated site not found at %s. Run builder.py first.", site_root
        )
        return False

    log.info("Deploying %s from %s ...", domain, site_root)

    # Step 1: Write Nginx config (HTTP only first, so certbot can challenge)
    write_nginx_config(domain, site_root, cfg)

    # Step 2: Validate config
    if not test_nginx_config():
        return False

    # Step 3: Reload Nginx so HTTP server is live for ACME challenge
    reload_nginx()

    # Step 4: Obtain SSL certificate
    if cfg.CERTBOT_EMAIL:
        ssl_ok = obtain_ssl_certificate(domain, cfg.CERTBOT_EMAIL, cfg.CERTBOT_WEBROOT)
        if not ssl_ok:
            log.warning(
                "SSL cert failed for %s — site will only be accessible over HTTP.", domain
            )
    else:
        log.warning("CERTBOT_EMAIL not set — skipping SSL for %s.", domain)

    # Step 5: Reload Nginx again to pick up SSL certs
    if not test_nginx_config():
        return False
    reload_nginx()

    # Step 6: Validate
    return validate_site(domain)


def deploy_all_sites() -> dict[str, bool]:
    """Deploy all configured domains. Returns {domain: success_bool}."""
    sys.path.insert(0, str(BUILDER_DIR.parent))
    from config import cfg  # noqa: PLC0415

    results: dict[str, bool] = {}
    for domain in cfg.SITE_DOMAINS:
        log.info("=== Deploying site: %s ===", domain)
        try:
            results[domain] = deploy_site(domain)
        except Exception as exc:
            log.error("Unexpected error deploying %s: %s", domain, exc, exc_info=True)
            results[domain] = False
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = deploy_all_sites()
    for domain, success in results.items():
        status = "✓ LIVE" if success else "✗ FAILED"
        print(f"  {domain}: {status}")
