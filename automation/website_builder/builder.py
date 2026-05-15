"""
website_builder/builder.py — Generates website content using OpenAI.

Reads reference files from website_builder/examples/ (or a urls.txt file),
then calls the OpenAI API to produce a complete, unique HTML/CSS/JS site
inspired by those references but with fresh content tailored to the domain.

Output is written to website_builder/generated/<domain>/.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

BUILDER_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BUILDER_DIR / "templates"
EXAMPLES_DIR = BUILDER_DIR / "examples"
GENERATED_DIR = BUILDER_DIR / "generated"

# Default template file used when no examples are provided
BASE_TEMPLATE = TEMPLATES_DIR / "base.html"

# Maximum bytes of reference content to include in the prompt
MAX_REFERENCE_BYTES = 12_000


def _get_openai_client():
    """Lazy-import and configure the OpenAI client."""
    try:
        from openai import OpenAI  # type: ignore[import]
    except ImportError:
        raise ImportError(
            "openai package is not installed. Run: pip install openai"
        )
    sys.path.insert(0, str(BUILDER_DIR.parent))
    from config import cfg  # noqa: PLC0415

    if not cfg.OPENAI_API_KEY:
        raise EnvironmentError(
            "OPENAI_API_KEY is not set. Add it to config.env."
        )
    return OpenAI(api_key=cfg.OPENAI_API_KEY), cfg


def _collect_references() -> str:
    """
    Read HTML files and urls.txt from the examples directory.
    Returns a combined string (truncated to MAX_REFERENCE_BYTES) for the prompt.
    """
    parts: list[str] = []

    # HTML files
    for html_file in sorted(EXAMPLES_DIR.glob("*.html")):
        content = html_file.read_text(errors="replace")[:4000]
        parts.append(f"=== Reference file: {html_file.name} ===\n{content}")

    # URLs file
    urls_file = EXAMPLES_DIR / "urls.txt"
    if urls_file.exists():
        try:
            import urllib.request  # noqa: PLC0415
            for line in urls_file.read_text().splitlines():
                url = line.strip()
                if not url or url.startswith("#"):
                    continue
                log.info("Fetching reference URL: %s", url)
                try:
                    with urllib.request.urlopen(url, timeout=10) as resp:
                        html = resp.read(6000).decode(errors="replace")
                    parts.append(f"=== Reference URL: {url} ===\n{html}")
                except Exception as exc:
                    log.warning("Could not fetch %s: %s", url, exc)
        except Exception as exc:
            log.warning("Error processing urls.txt: %s", exc)

    combined = "\n\n".join(parts)
    if len(combined.encode()) > MAX_REFERENCE_BYTES:
        combined = combined.encode()[:MAX_REFERENCE_BYTES].decode(errors="replace")

    return combined


def _build_prompt(
    domain: str,
    description: str,
    audience: str,
    template_html: str,
    references: str,
) -> str:
    ref_section = (
        f"\n\nREFERENCE EXAMPLES (study these for style and structure):\n{references}"
        if references.strip()
        else ""
    )
    return textwrap.dedent(f"""\
        You are a world-class web designer and copywriter.

        Generate a COMPLETE, production-ready, single-file HTML5 website for the following business.

        DOMAIN: {domain}
        DESCRIPTION: {description}
        TARGET AUDIENCE: {audience}
        YEAR: {datetime.now().year}
        {ref_section}

        BASE TEMPLATE (fill every {{{{PLACEHOLDER}}}} with real content):
        {template_html}

        REQUIREMENTS:
        1. Replace EVERY {{{{PLACEHOLDER}}}} with compelling, real, unique copy.
        2. Write the full page — every section must have real content.
        3. Keep all CSS variables intact; adjust colors to fit the brand if desired.
        4. Add 3 realistic feature cards with relevant icons (emoji).
        5. Add 3 pricing tiers: Starter / Pro / Enterprise — with realistic prices and feature lists.
        6. Add 3 genuine-sounding customer testimonials with different names and roles.
        7. Add 3 realistic "how it works" steps.
        8. Set {{{{YEAR}}}} to {datetime.now().year}.
        9. The contact form must post to /api/contact (already in the template).
        10. Include the Stripe payment integration script placeholder:
            <script src="/js/payment.js"></script> before </body>.
        11. Return ONLY the complete HTML file — no markdown fences, no explanation.
    """)


def _generate_html(client, cfg, domain: str, prompt: str) -> str:
    """Call OpenAI and return the raw HTML string."""
    log.info("Calling OpenAI (%s) to generate site for %s ...", cfg.OPENAI_MODEL, domain)
    response = client.chat.completions.create(
        model=cfg.OPENAI_MODEL,
        max_tokens=cfg.OPENAI_MAX_TOKENS,
        temperature=cfg.OPENAI_TEMPERATURE,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional web developer. "
                    "Output ONLY complete, valid HTML5. No markdown. No explanation."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content.strip()


def _write_payment_js(output_dir: Path, domain: str) -> None:
    """Write a Stripe payment initialisation stub."""
    js_dir = output_dir / "js"
    js_dir.mkdir(parents=True, exist_ok=True)
    js_file = js_dir / "payment.js"
    js_file.write_text(textwrap.dedent(f"""\
        // payment.js — Stripe initialisation for {domain}
        // The STRIPE_PUBLISHABLE_KEY is injected by the server at render time.
        (function () {{
          var pkMeta = document.querySelector('meta[name="stripe-pk"]');
          if (!pkMeta) return;
          var stripe = Stripe(pkMeta.content);
          document.querySelectorAll('[data-stripe-price-id]').forEach(function (btn) {{
            btn.addEventListener('click', function () {{
              fetch('/api/checkout', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ priceId: btn.dataset.stripePriceId }}),
              }})
              .then(function (r) {{ return r.json(); }})
              .then(function (data) {{
                if (data.url) window.location.href = data.url;
              }});
            }});
          }});
        }})();
    """))
    log.info("Written: %s", js_file)


def _write_site_meta(output_dir: Path, domain: str, description: str) -> None:
    """Write a robots.txt and sitemap.xml for the generated site."""
    (output_dir / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: https://{domain}/sitemap.xml\n"
    )
    today = datetime.now().strftime("%Y-%m-%d")
    (output_dir / "sitemap.xml").write_text(textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url>
            <loc>https://{domain}/</loc>
            <lastmod>{today}</lastmod>
            <changefreq>monthly</changefreq>
            <priority>1.0</priority>
          </url>
        </urlset>
    """))
    log.info("Written: robots.txt, sitemap.xml for %s", domain)


def build_site(domain: str) -> Path:
    """
    Generate a complete website for *domain* and write it to
    website_builder/generated/<domain>/.

    Returns the output directory path.
    """
    sys.path.insert(0, str(BUILDER_DIR.parent))
    from config import cfg  # noqa: PLC0415

    description = cfg.get_description_for(domain)
    audience = cfg.get_audience_for(domain)
    template_name = cfg.get_template_for(domain)

    template_file = TEMPLATES_DIR / f"{template_name}.html"
    if not template_file.exists():
        log.warning("Template '%s' not found, falling back to base.html.", template_name)
        template_file = BASE_TEMPLATE

    template_html = template_file.read_text()
    references = _collect_references()
    prompt = _build_prompt(domain, description, audience, template_html, references)

    client, cfg = _get_openai_client()
    html = _generate_html(client, cfg, domain, prompt)

    # Strip any accidental markdown fences
    html = re.sub(r"^```html\s*", "", html, flags=re.IGNORECASE)
    html = re.sub(r"```\s*$", "", html)

    # Write output
    output_dir = GENERATED_DIR / domain
    output_dir.mkdir(parents=True, exist_ok=True)

    index_html = output_dir / "index.html"
    index_html.write_text(html, encoding="utf-8")
    log.info("Generated index.html for %s (%d bytes)", domain, len(html.encode()))

    _write_payment_js(output_dir, domain)
    _write_site_meta(output_dir, domain, description)

    # Write a metadata sidecar for the deployer
    meta = {
        "domain": domain,
        "description": description,
        "audience": audience,
        "template": template_name,
        "generated_at": datetime.now().isoformat(),
    }
    (output_dir / ".site-meta.json").write_text(json.dumps(meta, indent=2))

    log.info("Site for %s written to %s", domain, output_dir)
    return output_dir


def build_all_sites() -> dict[str, Path]:
    """Build sites for all configured domains. Returns {domain: output_dir}."""
    sys.path.insert(0, str(BUILDER_DIR.parent))
    from config import cfg  # noqa: PLC0415

    results: dict[str, Path] = {}
    if not cfg.SITE_DOMAINS:
        log.warning("No SITE_DOMAINS configured — nothing to build.")
        return results

    for domain in cfg.SITE_DOMAINS:
        log.info("Building site for: %s", domain)
        try:
            results[domain] = build_site(domain)
        except Exception as exc:
            log.error("Failed to build site for %s: %s", domain, exc, exc_info=True)

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = build_all_sites()
    for domain, path in results.items():
        print(f"  {domain} → {path}")
