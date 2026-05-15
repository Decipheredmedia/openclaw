#!/usr/bin/env python3
"""
install.py — Master installer for the OpenClaw Automation System.

Installs all system dependencies, clones and builds openclaw, deploys it as a
systemd service, and wires it into Nginx with SSL via Let's Encrypt.

Must be run as root (or via sudo) on Ubuntu 22.04+.

Usage:
    sudo python3 install.py
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("installer")

# ---------------------------------------------------------------------------
# Paths relative to this script
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
SYSTEMD_UNIT_SRC = SCRIPT_DIR / "systemd" / "openclaw-automation.service"
SYSTEMD_UNIT_DST = Path("/etc/systemd/system/openclaw-automation.service")
OPENCLAW_SYSTEMD_SRC = SCRIPT_DIR / "systemd" / "openclaw-gateway.service"
OPENCLAW_SYSTEMD_DST = Path("/etc/systemd/system/openclaw-gateway.service")


# ---------------------------------------------------------------------------
# Shell helpers
# ---------------------------------------------------------------------------

def run(cmd: str | list[str], check: bool = True, capture: bool = False, **kwargs) -> subprocess.CompletedProcess:
    """Run a shell command, logging it first."""
    if isinstance(cmd, str):
        log.info("$ %s", cmd)
        result = subprocess.run(cmd, shell=True, capture_output=capture, text=True, **kwargs)
    else:
        log.info("$ %s", " ".join(str(c) for c in cmd))
        result = subprocess.run(cmd, capture_output=capture, text=True, **kwargs)
    if check and result.returncode != 0:
        if capture:
            log.error("STDOUT: %s", result.stdout)
            log.error("STDERR: %s", result.stderr)
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {cmd}")
    return result


def apt_install(*packages: str) -> None:
    run(f"apt-get install -y {' '.join(packages)}")


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


# ---------------------------------------------------------------------------
# Installation steps
# ---------------------------------------------------------------------------

def check_root() -> None:
    if os.geteuid() != 0:
        log.error("This installer must be run as root. Try: sudo python3 install.py")
        sys.exit(1)


def update_apt() -> None:
    log.info("=== Updating apt package lists ===")
    run("apt-get update -y")
    run("DEBIAN_FRONTEND=noninteractive apt-get upgrade -y")


def install_system_deps() -> None:
    log.info("=== Installing system dependencies ===")
    # Base utilities
    apt_install(
        "curl", "wget", "git", "unzip", "gnupg2", "ca-certificates",
        "lsb-release", "software-properties-common", "build-essential",
        "nginx", "certbot", "python3-certbot-nginx",
        "python3.11", "python3.11-venv", "python3-pip",
        "sqlite3", "ufw",
    )


def install_nodejs() -> None:
    log.info("=== Installing Node.js 22 ===")
    if command_exists("node"):
        result = run("node --version", capture=True)
        ver = result.stdout.strip()
        major = int(ver.lstrip("v").split(".")[0]) if ver.startswith("v") else 0
        if major >= 22:
            log.info("Node.js %s already installed — skipping.", ver)
            return
    run("curl -fsSL https://deb.nodesource.com/setup_22.x | bash -")
    apt_install("nodejs")
    ver = run("node --version", capture=True).stdout.strip()
    log.info("Node.js %s installed.", ver)


def install_pnpm() -> None:
    log.info("=== Installing pnpm ===")
    if command_exists("pnpm"):
        log.info("pnpm already installed — skipping.")
        return
    run("npm install -g pnpm")
    log.info("pnpm installed.")


def clone_openclaw(openclaw_dir: str, repo_url: str, branch: str) -> None:
    log.info("=== Cloning openclaw ===")
    dest = Path(openclaw_dir)
    if dest.exists():
        log.info("openclaw already cloned at %s — pulling latest.", openclaw_dir)
        run(f"git -C {openclaw_dir} fetch origin")
        run(f"git -C {openclaw_dir} checkout {branch}")
        run(f"git -C {openclaw_dir} pull --rebase origin {branch}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    run(f"git clone --branch {branch} {repo_url} {openclaw_dir}")
    log.info("openclaw cloned to %s", openclaw_dir)


def build_openclaw(openclaw_dir: str) -> None:
    log.info("=== Building openclaw (pnpm install && pnpm build) ===")
    run(f"pnpm --dir {openclaw_dir} install --frozen-lockfile")
    run(f"pnpm --dir {openclaw_dir} build")
    log.info("openclaw built successfully.")


def write_openclaw_systemd(openclaw_dir: str, bind: str, port: int) -> None:
    log.info("=== Writing openclaw-gateway systemd unit ===")
    unit = textwrap.dedent(f"""\
        [Unit]
        Description=OpenClaw Gateway
        After=network.target
        Wants=network-online.target

        [Service]
        Type=simple
        User=root
        WorkingDirectory={openclaw_dir}
        ExecStart=/usr/bin/env pnpm openclaw gateway run --bind {bind} --port {port} --force
        Restart=always
        RestartSec=5
        StandardOutput=journal
        StandardError=journal
        SyslogIdentifier=openclaw-gateway
        Environment=NODE_ENV=production

        [Install]
        WantedBy=multi-user.target
    """)
    OPENCLAW_SYSTEMD_DST.write_text(unit)
    log.info("Written: %s", OPENCLAW_SYSTEMD_DST)


def write_automation_systemd(automation_dir: str) -> None:
    log.info("=== Writing openclaw-automation systemd unit ===")
    if SYSTEMD_UNIT_SRC.exists():
        shutil.copy(SYSTEMD_UNIT_SRC, SYSTEMD_UNIT_DST)
        log.info("Copied: %s → %s", SYSTEMD_UNIT_SRC, SYSTEMD_UNIT_DST)
        return
    # Generate a sensible default if the file doesn't exist yet
    unit = textwrap.dedent(f"""\
        [Unit]
        Description=OpenClaw Automation System
        After=network.target openclaw-gateway.service
        Wants=openclaw-gateway.service

        [Service]
        Type=simple
        User=root
        WorkingDirectory={automation_dir}
        ExecStart=/usr/bin/python3 {automation_dir}/main.py --start
        Restart=always
        RestartSec=10
        StandardOutput=journal
        StandardError=journal
        SyslogIdentifier=openclaw-automation

        [Install]
        WantedBy=multi-user.target
    """)
    SYSTEMD_UNIT_DST.write_text(unit)
    log.info("Written: %s", SYSTEMD_UNIT_DST)


def enable_services() -> None:
    log.info("=== Enabling and starting services ===")
    run("systemctl daemon-reload")
    for svc in ("nginx", "openclaw-gateway", "openclaw-automation"):
        run(f"systemctl enable {svc}")
        run(f"systemctl start {svc}")
        log.info("Service %s enabled and started.", svc)


def configure_nginx_proxy(openclaw_dir: str, port: int) -> None:
    """Write a basic Nginx reverse-proxy config for the openclaw gateway."""
    log.info("=== Writing Nginx proxy config for openclaw gateway ===")
    conf = textwrap.dedent(f"""\
        # OpenClaw Gateway reverse proxy
        # Managed by openclaw-automation installer — do not edit manually.
        server {{
            listen 80;
            server_name _;

            location /openclaw/ {{
                proxy_pass http://127.0.0.1:{port}/;
                proxy_set_header Host $host;
                proxy_set_header X-Real-IP $remote_addr;
                proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                proxy_set_header X-Forwarded-Proto $scheme;
                proxy_http_version 1.1;
                proxy_set_header Upgrade $http_upgrade;
                proxy_set_header Connection "upgrade";
            }}
        }}
    """)
    conf_path = Path("/etc/nginx/sites-available/openclaw-gateway.conf")
    conf_path.write_text(conf)
    link = Path("/etc/nginx/sites-enabled/openclaw-gateway.conf")
    if not link.exists():
        link.symlink_to(conf_path)
    run("nginx -t")
    run("systemctl reload nginx")
    log.info("Nginx proxy configured.")


def obtain_ssl(domains: list[str], email: str, webroot: str) -> None:
    """Obtain Let's Encrypt certificates for each domain."""
    if not domains or not email:
        log.warning("No domains or certbot email configured — skipping SSL.")
        return
    log.info("=== Obtaining SSL certificates via Certbot ===")
    Path(webroot).mkdir(parents=True, exist_ok=True)
    for domain in domains:
        log.info("Obtaining certificate for %s ...", domain)
        result = run(
            f"certbot certonly --webroot -w {webroot} -d {domain} "
            f"--non-interactive --agree-tos -m {email}",
            check=False,
            capture=True,
        )
        if result.returncode == 0:
            log.info("Certificate obtained for %s.", domain)
        else:
            log.warning(
                "Certbot failed for %s (may already exist or DNS not ready):\n%s",
                domain,
                result.stderr,
            )


def install_python_deps(automation_dir: str) -> None:
    log.info("=== Installing Python dependencies ===")
    req = Path(automation_dir) / "requirements.txt"
    if not req.exists():
        log.warning("requirements.txt not found at %s — skipping pip install.", req)
        return
    run(f"python3.11 -m pip install --upgrade pip")
    run(f"python3.11 -m pip install -r {req}")
    log.info("Python dependencies installed.")


def configure_ufw() -> None:
    log.info("=== Configuring UFW firewall ===")
    for rule in ("ssh", "http", "https"):
        run(f"ufw allow {rule}", check=False)
    run("ufw --force enable", check=False)
    log.info("UFW configured.")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenClaw Automation Installer")
    parser.add_argument(
        "--skip-apt", action="store_true",
        help="Skip apt package installation (useful if already installed)"
    )
    parser.add_argument(
        "--skip-build", action="store_true",
        help="Skip pnpm install/build for openclaw"
    )
    parser.add_argument(
        "--skip-ssl", action="store_true",
        help="Skip Let's Encrypt certificate issuance"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    check_root()

    # Load config
    sys.path.insert(0, str(SCRIPT_DIR))
    from config import cfg  # noqa: PLC0415

    log.info("Starting OpenClaw Automation installer...")
    log.info("openclaw directory : %s", cfg.OPENCLAW_DIR)
    log.info("automation directory: %s", cfg.AUTOMATION_DIR)

    if not args.skip_apt:
        update_apt()
        install_system_deps()
        install_nodejs()
        install_pnpm()

    clone_openclaw(cfg.OPENCLAW_DIR, cfg.OPENCLAW_REPO, cfg.OPENCLAW_BRANCH)

    if not args.skip_build:
        build_openclaw(cfg.OPENCLAW_DIR)

    write_openclaw_systemd(cfg.OPENCLAW_DIR, cfg.OPENCLAW_BIND, cfg.OPENCLAW_PORT)
    write_automation_systemd(cfg.AUTOMATION_DIR)
    install_python_deps(cfg.AUTOMATION_DIR)
    configure_nginx_proxy(cfg.OPENCLAW_DIR, cfg.OPENCLAW_PORT)

    if not args.skip_ssl:
        obtain_ssl(cfg.SITE_DOMAINS, cfg.CERTBOT_EMAIL, cfg.CERTBOT_WEBROOT)

    enable_services()
    configure_ufw()

    log.info("")
    log.info("=" * 60)
    log.info("Installation complete!")
    log.info("  openclaw gateway  : http://127.0.0.1:%d", cfg.OPENCLAW_PORT)
    log.info("  Automation system : systemctl status openclaw-automation")
    log.info("  Telegram bot      : running inside openclaw-automation service")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
