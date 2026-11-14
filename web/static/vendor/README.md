# Vendored third-party assets

Everything in this folder is a **local copy** of a third-party asset that used
to be loaded from a public CDN (`cdn.jsdelivr.net`, `cdnjs.cloudflare.com`,
`code.jquery.com`, `fonts.googleapis.com`).

They are served from `/static/vendor/...` so the app renders identically on a
machine without internet access (offline tablet, air-gapped server, blocked
egress).  Do **not** point a template back at a CDN: the test
`tests/test_no_external_cdn_assets.py` fails when that happens.

| Path | Version | Upstream |
| --- | --- | --- |
| `bootstrap-5.3.2/` | 5.3.2 | https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/ |
| `jquery-3.6.0/` | 3.6.0 | https://code.jquery.com/jquery-3.6.0.min.js |
| `chartjs/chart.umd.min.js` | 4.5.1 | https://cdn.jsdelivr.net/npm/chart.js |
| `fabric-5.3.1/` | 5.3.1 | https://cdnjs.cloudflare.com/ajax/libs/fabric.js/5.3.1/ |
| `fontawesome-6.5.1/` | 6.5.1 | https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/ |
| `fonts/` | - | https://fonts.googleapis.com/css2 (Bebas Neue, Outfit, Inter, Barlow Condensed) |

Notes:

* `fontawesome-6.5.1/css/all.min.css` resolves its fonts through
  `../webfonts/...`, therefore `css/` and `webfonts/` have to stay siblings.
  Both the `woff2` files and the legacy `ttf` fallbacks are kept so the
  stylesheet stays byte-identical to the upstream release.
* `fonts/fonts.css` is the Google Fonts stylesheet with every `url()`
  rewritten to the sibling `*.woff2` files (latin / latin-ext subsets only).
* The files are byte-for-byte copies of the upstream releases - do not edit
  them, re-download them instead and record the new version in the table
  above.

## Licenses

* Bootstrap - MIT
* jQuery - MIT
* Chart.js - MIT
* Fabric.js - MIT
* Font Awesome Free - CC BY 4.0 (icons) / SIL OFL 1.1 (fonts) / MIT (code)
* Bebas Neue - SIL Open Font License 1.1
* Outfit - SIL Open Font License 1.1
* Inter - SIL Open Font License 1.1
* Barlow Condensed - SIL Open Font License 1.1
