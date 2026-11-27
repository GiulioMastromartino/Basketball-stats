"""Guard rails against third-party CDN dependencies.

Every page used to pull Bootstrap, jQuery, Font Awesome, Chart.js, Fabric.js
and the Google webfonts straight from a public CDN.  As soon as the machine
loses internet access (offline tablet, air-gapped server, blocked egress)
*every* page loses its stylesheet, its JavaScript and its icons - and the
inline scripts that depend on jQuery die with
``ReferenceError: $ is not defined``.

The assets are now vendored under ``web/static/vendor`` and served from
``/static``.  These tests lock that in:

* no template may point a ``<script src>``, ``<link href>`` or a CSS
  ``@import`` at an external host (a small, documented allowlist exists for
  the WeasyPrint PDF templates);
* every asset referenced by a template or by the vendored CSS has to exist
  under ``web/static``;
* the shell declares a favicon;
* a template whose inline script uses jQuery gets jQuery from the vendored
  copy (directly or through its parent layout).
"""

import re
from pathlib import Path

import pytest


# =============================================================================
# Paths & constants
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "web" / "templates"
STATIC_DIR = REPO_ROOT / "web" / "static"
VENDOR_DIR = STATIC_DIR / "vendor"

#: Hosts that must never be referenced from a template at runtime.
FORBIDDEN_HOSTS = {
    "cdn.jsdelivr.net",
    "cdnjs.cloudflare.com",
    "cdnjs.com",
    "code.jquery.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "ajax.googleapis.com",
    "unpkg.com",
    "cdn.bootcdn.net",
    "stackpath.bootstrapcdn.com",
    "maxcdn.bootstrapcdn.com",
    "cdn.skypack.dev",
    "esm.sh",
}

#: ``(template path relative to the repo root, host) -> reason``.
#:
#: Every entry must explain *why* an external reference is acceptable.  The
#: PDF templates are rendered by WeasyPrint in a background job, they never
#: serve assets to a browser and the remote font is a nice-to-have for the
#: printed layout only.
EXTERNAL_REFERENCE_ALLOWLIST = {
    (
        "web/templates/team_report_pdf.html",
        "fonts.googleapis.com",
    ): (
        "PDF template rendered by WeasyPrint (core/services/report_service.py). "
        "It is never served to a browser and the remote font only affects the "
        "printed PDF; the interactive pages use the vendored fonts."
    ),
    (
        "web/templates/reports/lineup_report.html",
        "fonts.googleapis.com",
    ): (
        "PDF template rendered by WeasyPrint (core/advanced_pdf_reports.py). "
        "It is never served to a browser and the remote font only affects the "
        "printed PDF; the interactive pages use the vendored fonts."
    ),
    (
        "web/templates/reports/lineup_report.html",
        "fonts.gstatic.com",
    ): (
        "preconnect hint for the WeasyPrint PDF font - see above."
    ),
    (
        "web/templates/reports/player_scouting_card.html",
        "fonts.googleapis.com",
    ): (
        "PDF template rendered by WeasyPrint (core/advanced_pdf_reports.py). "
        "It is never served to a browser and the remote font only affects the "
        "printed PDF; the interactive pages use the vendored fonts."
    ),
    (
        "web/templates/reports/player_scouting_card.html",
        "fonts.gstatic.com",
    ): (
        "preconnect hint for the WeasyPrint PDF font - see above."
    ),
    (
        "web/templates/reports/season_trend_report.html",
        "fonts.googleapis.com",
    ): (
        "PDF template rendered by WeasyPrint (core/advanced_pdf_reports.py). "
        "It is never served to a browser and the remote font only affects the "
        "printed PDF; the interactive pages use the vendored fonts."
    ),
    (
        "web/templates/reports/season_trend_report.html",
        "fonts.gstatic.com",
    ): (
        "preconnect hint for the WeasyPrint PDF font - see above."
    ),
    (
        "web/templates/reports/clutch_report.html",
        "fonts.googleapis.com",
    ): (
        "PDF template rendered by WeasyPrint (core/advanced_pdf_reports.py). "
        "It is never served to a browser and the remote font only affects the "
        "printed PDF; the interactive pages use the vendored fonts."
    ),
    (
        "web/templates/reports/clutch_report.html",
        "fonts.gstatic.com",
    ): (
        "preconnect hint for the WeasyPrint PDF font - see above."
    ),
    (
        "web/templates/live_game.html",
        "code.jquery.com",
    ): (
        "Redundant duplicate: base_live.html (the parent layout of this "
        "template) already loads the vendored /static/vendor/jquery-3.6.0 "
        "copy, so the page works offline.  The stale CDN tag is left in place "
        "because live_game.html is owned by another work stream; removing it is "
        "a one-line follow-up."
    ),
    (
        "web/templates/landing.html",
        "fonts.googleapis.com",
    ): (
        "Legacy landing page variant, not rendered by any route "
        "(web/routes/main.py renders landing_oss.html).  Kept only as a "
        "design reference."
    ),
    (
        "web/templates/landing.html",
        "fonts.gstatic.com",
    ): (
        "Legacy landing page variant, not rendered by any route - see above."
    ),
    (
        "web/templates/landing.html",
        "cdnjs.cloudflare.com",
    ): (
        "Legacy landing page variant, not rendered by any route - see above."
    ),
    (
        "web/templates/landing.current.html",
        "fonts.googleapis.com",
    ): (
        "Legacy landing page variant, not rendered by any route - see above."
    ),
    (
        "web/templates/landing.current.html",
        "fonts.gstatic.com",
    ): (
        "Legacy landing page variant, not rendered by any route - see above."
    ),
    (
        "web/templates/landing.current.html",
        "cdnjs.cloudflare.com",
    ): (
        "Legacy landing page variant, not rendered by any route - see above."
    ),
    (
        "web/templates/landing.toomuch.html",
        "fonts.googleapis.com",
    ): (
        "Legacy landing page variant, not rendered by any route - see above."
    ),
    (
        "web/templates/landing.toomuch.html",
        "fonts.gstatic.com",
    ): (
        "Legacy landing page variant, not rendered by any route - see above."
    ),
    (
        "web/templates/landing.toomuch.html",
        "cdnjs.cloudflare.com",
    ): (
        "Legacy landing page variant, not rendered by any route - see above."
    ),
}


# =============================================================================
# Helpers
# =============================================================================

_SCRIPT_SRC_RE = re.compile(
    r"<script\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE
)
_LINK_HREF_RE = re.compile(
    r"<link\b[^>]*?\bhref\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE
)
_IMPORT_RE = re.compile(r"@import\s+(?:url\()?\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_CSS_URL_RE = re.compile(r"url\(\s*[\"']?([^\"')]+)[\"']?\s*\)", re.IGNORECASE)
_STATIC_REF_RE = re.compile(
    r"(?:static_url|url_for\s*\(\s*[\"']static[\"']\s*,\s*filename\s*=\s*)"
    r"\(?\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_JINQUINY_COMMENT_RE = re.compile(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.DOTALL)
_EXTENDS_RE = re.compile(r"\{%\s*extends\s+[\"']([^\"']+)[\"']")

#: ``<link>`` relations that never point at a stylesheet/font asset.
_NON_ASSET_LINK_RELS = {
    "canonical",
    "alternate",
    "preconnect",
    "dns-prefetch",
    "prerender",
    "prefetch",
    "manifest",
}


def _template_files():
    return sorted(TEMPLATES_DIR.rglob("*.html"))


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _strip_comments(text: str) -> str:
    text = _COMMENT_RE.sub(" ", text)
    return _JINQUINY_COMMENT_RE.sub(" ", text)


def _host_of(url: str):
    """Return the lowercase host of *url* or ``None`` for local references."""
    match = re.match(r"^\s*(?:https?:)?//([^/\s\"'#?]+)", url, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).split("@")[-1].split(":")[0].lower()


def _external_references(path: Path):
    """Yield ``(host, url, kind)`` for every external asset reference."""
    text = path.read_text(encoding="utf-8", errors="replace")

    for url in _SCRIPT_SRC_RE.findall(text):
        host = _host_of(url)
        if host:
            yield host, url, "script src"

    for tag in re.findall(r"<link\b[^>]*>", text, re.IGNORECASE):
        href_match = re.search(r"\bhref\s*=\s*[\"']([^\"']+)[\"']", tag, re.IGNORECASE)
        if not href_match:
            continue
        rel_match = re.search(r"\brel\s*=\s*[\"']([^\"']+)[\"']", tag, re.IGNORECASE)
        rel = (rel_match.group(1).lower() if rel_match else "")
        if rel in _NON_ASSET_LINK_RELS:
            # preconnect/dns-prefetch hints are not assets, but they still mean
            # "this page wants to talk to a CDN" - keep them out of the app.
            url = href_match.group(1)
            host = _host_of(url)
            if host:
                yield host, url, "link rel=%s" % rel
            continue
        url = href_match.group(1)
        host = _host_of(url)
        if host:
            yield host, url, "link href"

    for url in _IMPORT_RE.findall(text):
        host = _host_of(url)
        if host:
            yield host, url, "css @import"


def _layout_chain(path: Path, cache=None):
    """Return ``[template, parent, grandparent, ...]`` for *path*."""
    if cache is None:
        cache = {}
    if path in cache:
        return cache[path]

    cache[path] = [path]  # guard against cycles
    text = path.read_text(encoding="utf-8", errors="replace")
    match = _EXTENDS_RE.search(text)
    if match:
        parent = (path.parent / match.group(1)).resolve()
        if parent.exists():
            chain = [path] + _layout_chain(parent, cache)
            cache[path] = chain
            return chain
    cache[path] = [path]
    return cache[path]


def _uses_jquery(text: str) -> bool:
    body = _strip_comments(text)
    return bool(
        re.search(r"(?<![\w$])\$\s*\(", body)
        or re.search(r"(?<![\w$])\$\s*\.", body)
        or re.search(r"\bjQuery\b", body)
    )


# =============================================================================
# Tests
# =============================================================================


def test_templates_exist():
    assert _template_files(), "no templates found - the glob is wrong"


def test_no_template_references_an_external_cdn():
    """No <script>/<link>/@import may point at a third-party CDN."""
    offenders = []
    for template in _template_files():
        for host, url, kind in _external_references(template):
            if ( _rel(template), host) in EXTERNAL_REFERENCE_ALLOWLIST:
                continue
            offenders.append(
                "%s: %s -> %s" % (_rel(template), kind, url)
            )
    assert not offenders, (
        "Templates must not load assets from an external CDN.\n"
        "Vendor the asset under web/static/vendor and reference it with "
        "url_for('static', ...) instead:\n  - " + "\n  - ".join(offenders)
    )


def test_external_reference_allowlist_is_documented_and_used():
    """Every allowlist entry must exist and must actually be needed."""
    stale = []
    for (rel_path, host), reason in EXTERNAL_REFERENCE_ALLOWLIST.items():
        template = REPO_ROOT / rel_path
        if not template.exists():
            stale.append("%s does not exist any more" % rel_path)
            continue
        if not reason or len(reason) < 20:
            stale.append("%s (%s) has no explanatory comment" % (rel_path, host))
            continue
        hosts = {h for h, _u, _k in _external_references(template)}
        if host not in hosts:
            stale.append(
                "%s no longer references %s - drop it from the allowlist"
                % (rel_path, host)
            )
    assert not stale, "stale allowlist entries:\n  - " + "\n  - ".join(stale)


def test_no_forbidden_host_is_allowlisted():
    """The allowlist may only cover the documented exceptions."""
    allowed_hosts = {
        # WeasyPrint PDF templates: the remote font only affects the PDF.
        "fonts.googleapis.com",
        "fonts.gstatic.com",
        # Redundant duplicate in live_game.html - base_live.html already
        # ships the vendored jQuery.
        "code.jquery.com",
        # Legacy landing page variants that no route renders.
        "cdnjs.cloudflare.com",
    }
    for (rel_path, host) in EXTERNAL_REFERENCE_ALLOWLIST:
        assert host in allowed_hosts, (
            "%s allows the unexpected host %s" % (rel_path, host)
        )


def test_vendor_assets_are_present():
    """The vendored copies of every third-party library must be committed."""
    expected = [
        "bootstrap-5.3.2/bootstrap.min.css",
        "bootstrap-5.3.2/bootstrap.bundle.min.js",
        "jquery-3.6.0/jquery.min.js",
        "chartjs/chart.umd.min.js",
        "fabric-5.3.1/fabric.min.js",
        "fontawesome-6.5.1/css/all.min.css",
        "fontawesome-6.5.1/webfonts/fa-solid-900.woff2",
        "fontawesome-6.5.1/webfonts/fa-regular-400.woff2",
        "fontawesome-6.5.1/webfonts/fa-brands-400.woff2",
        "fontawesome-6.5.1/webfonts/fa-v4compatibility.woff2",
        "fonts/fonts.css",
    ]
    missing = [name for name in expected if not (VENDOR_DIR / name).is_file()]
    assert not missing, "missing vendored assets:\n  - " + "\n  - ".join(missing)


def test_vendored_css_references_exist():
    """Every url() inside the vendored/app CSS must resolve to a real file."""
    problems = []
    for css in sorted(STATIC_DIR.rglob("*.css")):
        text = css.read_text(encoding="utf-8", errors="replace")
        for raw in _CSS_URL_RE.findall(text):
            url = raw.strip()
            if not url or url.startswith(("data:", "http://", "https://", "//", "#")):
                continue
            target = (css.parent / url.split("?")[0].split("#")[0]).resolve()
            if not target.exists():
                problems.append(
                    "%s references %s" % (_rel(css), url)
                )
    assert not problems, (
        "Broken asset references in CSS:\n  - " + "\n  - ".join(problems)
    )


def test_vendored_font_stylesheet_references_exist():
    """The local webfont stylesheet must only point at local woff2 files."""
    fonts_css = VENDOR_DIR / "fonts" / "fonts.css"
    assert fonts_css.is_file(), "the local webfont stylesheet is missing"
    text = fonts_css.read_text(encoding="utf-8", errors="replace")
    urls = [u.strip() for u in _CSS_URL_RE.findall(text)]
    assert urls, "the webfont stylesheet declares no @font-face"
    for url in urls:
        assert not url.startswith(("http://", "https://", "//")), (
            "the local webfont stylesheet still points at a remote host: %s" % url
        )
        target = (fonts_css.parent / url.split("?")[0].split("#")[0]).resolve()
        assert target.is_file(), (
            "the local webfont stylesheet points at a missing file: %s" % url
        )


def test_template_static_references_exist():
    """Every ``url_for('static', ...)`` / ``static_url(...)`` must resolve.

    Runtime content (uploaded play drawings, demo videos) is created at
    runtime and is therefore excluded - only the shipped assets have to be
    present in the repository.
    """
    runtime_prefixes = ("uploads/", "videos/")
    problems = []
    for template in _template_files():
        text = template.read_text(encoding="utf-8", errors="replace")
        for name in _STATIC_REF_RE.findall(text):
            if name.startswith(runtime_prefixes) or name.endswith("/"):
                continue
            target = (STATIC_DIR / name).resolve()
            if not target.exists():
                problems.append("%s -> static/%s" % (_rel(template), name))
    assert not problems, (
        "Templates point at static files that do not exist:\n  - "
        + "\n  - ".join(problems)
    )


def test_favicon_is_declared():
    """The shell must declare the local favicon (no more /favicon.ico 404)."""
    for name in ("base.html", "base_live.html"):
        template = TEMPLATES_DIR / name
        text = template.read_text(encoding="utf-8", errors="replace")
        assert re.search(
            r"<link\b[^>]*\brel\s*=\s*[\"']icon[\"'][^>]*>", text, re.IGNORECASE
        ), "%s does not declare a favicon" % name
        assert "basketball_icon.svg" in text, (
            "%s does not use the local favicon" % name
        )


@pytest.mark.parametrize(
    "template",
    ["base.html", "base_live.html", "plays/layout_fullscreen.html"],
)
def test_shell_loads_vendored_assets(template):
    """The HTML shell must reference the vendored copies, not a CDN."""
    text = (TEMPLATES_DIR / template).read_text(encoding="utf-8", errors="replace")
    assert "vendor/bootstrap-5.3.2/bootstrap.min.css" in text
    assert "vendor/bootstrap-5.3.2/bootstrap.bundle.min.js" in text
    assert "vendor/jquery-3.6.0/jquery.min.js" in text
    assert "vendor/fontawesome-6.5.1/css/all.min.css" in text
    assert "vendor/fonts/fonts.css" in text


def test_templates_using_jquery_get_it_from_the_vendor_directory():
    """Inline scripts must not depend on a CDN-provided jQuery.

    A template whose inline script uses ``$``/``jQuery`` has to load the
    vendored jQuery itself or inherit it from its parent layout, otherwise
    the page dies with ``ReferenceError: $ is not defined`` whenever the
    asset cannot be fetched.
    """
    cache = {}
    problems = []
    for template in _template_files():
        text = template.read_text(encoding="utf-8", errors="replace")
        if not _uses_jquery(text):
            continue
        chain = _layout_chain(template, cache)
        sources = "\n".join(
            part.read_text(encoding="utf-8", errors="replace") for part in chain
        )
        if "vendor/jquery-3.6.0/jquery.min.js" not in sources:
            problems.append(
                "%s uses jQuery but none of %s loads the vendored copy"
                % (_rel(template), " / ".join(_rel(p) for p in chain))
            )
    assert not problems, "\n".join(problems)
