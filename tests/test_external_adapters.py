"""Tests for the championship scraper adapters (offline fixtures)."""

from jobs.adapters import fip_api
from jobs.adapters import playbasket_html as pb


CALENDAR_HTML = """
<table><tr><th>Data</th><th>Casa</th><th>Ospite</th><th></th><th>PC</th><th>PO</th></tr>
<tr><td>16/10</td><td>Leone XIII Milano sq.B</td><td>Aurora Milano sq.B</td><td></td><td>68</td><td>60</td></tr>
<tr><td>17/10</td><td>Team X</td><td>Team Y</td><td></td><td></td><td></td></tr>
</table>
"""

CALENDAR_HTML_LINKED = """
<table><tr><td class="small"><a href="match.php?x=1">16/10</a></td>
<td class="large"><a href="match.php?x=1">Leone XIII Milano sq.B</a></td>
<td class="large winner_team"><a href="match.php?x=1">Aurora Milano sq.B</a></td>
<td></td><td>68</td><td>60</td></tr>
</table>
"""


STANDINGS_HTML = """
<table><tr><th>#</th><th>Squadra</th><th>P.ti</th><th>P.ti/P</th><th>G</th>
<th>V</th><th>P</th><th>%</th><th>S</th><th>PF</th><th>PS</th></tr>
<tr><td>1</td><td>Leone XIII Milano sq.B</td><td>42</td><td>1.91</td><td>22</td>
<td>21</td><td>1</td><td>.955</td><td>8W</td><td>1660</td><td>1210</td></tr>
</table>
"""


class TestPlaybasketAdapter:
    def test_parse_calendar_skips_unplayed(self):
        games = pb.parse_calendar(CALENDAR_HTML)
        assert len(games) == 1
        assert games[0]["home"] == "Leone XIII Milano sq.B"
        assert games[0]["home_score"] == "68"

    def test_parse_standings(self):
        rows = pb.parse_standings(STANDINGS_HTML)
        assert len(rows) == 1
        assert rows[0] == {"pos": 1, "team": "Leone XIII Milano sq.B",
                           "pts": 42, "g": 22, "w": 21, "l": 1,
                           "pf": 1660, "ps": 1210}

    def test_fingerprint_stable_on_scores(self):
        assert (pb.page_fingerprint(CALENDAR_HTML)
                == pb.page_fingerprint(CALENDAR_HTML.replace("68", "70")))

    def test_parse_calendar_includes_scheduled_on_request(self):
        games = pb.parse_calendar(CALENDAR_HTML, include_scheduled=True)
        assert len(games) == 2
        scheduled = games[1]
        assert scheduled["status"] == "scheduled"
        assert scheduled["home"] == "Team X"
        assert scheduled["home_score"] == ""

    def test_league_title(self):
        assert (pb.league_title("<title>Calendario Girone A | Est</title>")
                == "Calendario Girone A | Est")

    def test_parse_calendar_link_wrapped_cells(self):
        # Current Playbasket markup wraps every cell in <a> links.
        games = pb.parse_calendar(CALENDAR_HTML_LINKED)
        assert len(games) == 1
        assert games[0]["home"] == "Leone XIII Milano sq.B"
        assert games[0]["away"] == "Aurora Milano sq.B"
        assert games[0]["home_score"] == "68"

    def test_resolve_girone_id_from_index(self, monkeypatch):
        index = ('<a href="league.php?lt=2&lf=M&lr=LO&lp=MI&lc=DR3'
                 '&season=2027&lg=3&mod=gr">Girone C</a>')
        monkeypatch.setattr(pb, "_fetch", lambda url: index)
        assert (pb.resolve_girone_id("MI", "DR3", "2027", "c") == "3")

    def test_resolve_girone_id_unescapes_html_entities(self, monkeypatch):
        # Playbasket templates escape query separators as &amp;.
        index = ('<a href="league.php?lt=2&amp;lf=M&amp;lr=LO&amp;lp=MI'
                 '&amp;lc=DR4&amp;season=2026&amp;lg=13&amp;mod=gr">'
                 'Girone M</a>')
        monkeypatch.setattr(pb, "_fetch", lambda url: index)
        assert (pb.resolve_girone_id("MI", "DR4", "2026", "m") == "13")

    def test_resolve_girone_id_rejects_wrong_league(self, monkeypatch):
        index = ('<a href="league.php?lt=2&lf=M&lr=LO&lp=MI&lc=DR4'
                 '&season=2027&lg=13&mod=gr">Girone M</a>')
        monkeypatch.setattr(pb, "_fetch", lambda url: index)
        try:
            pb.resolve_girone_id("MI", "DR3", "2027", "M")
            assert False, "should have raised"
        except ValueError as exc:
            assert "does not exist" in str(exc)

    def test_resolve_girone_id_static_fallback_offline(self, monkeypatch):
        monkeypatch.setattr(pb, "_fetch",
                            lambda url: (_ for _ in ()).throw(
                                TimeoutError("down")))
        assert pb.resolve_girone_id("MI", "DR4", "2026", "M") == "13"


class TestFipDiscoverGironi:
    PAGE = """
    <select name="gironi">
    <option value="85404">Girone G</option>
    <option value="85405">Girone H</option>
    <option value="85406">Girone I</option>
    </select>
    """

    def _fake_urlopen(self, monkeypatch, html):
        import urllib.request

        class FakeHeaders:
            def get_content_charset(self):
                return "utf-8"

        class FakeResp:
            headers = FakeHeaders()

            def read(self):
                return html.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda req, timeout=25: FakeResp())

    def test_discovers_numeric_ids(self, monkeypatch):
        self._fake_urlopen(monkeypatch, self.PAGE)
        gironi = fip_api.discover_gironi("RLO", "1DM", "1", "M")
        assert gironi == [
            {"code": "85404", "label": "Girone G"},
            {"code": "85405", "label": "Girone H"},
            {"code": "85406", "label": "Girone I"},
        ]

    def test_empty_without_select(self, monkeypatch):
        self._fake_urlopen(monkeypatch, "<html><body>niente</body></html>")
        assert fip_api.discover_gironi("RLO", "1DM") == []

    def test_sends_fase_and_sex(self, monkeypatch):
        import urllib.request

        seen = {}
        page = self.PAGE

        class FakeHeaders:
            def get_content_charset(self):
                return "utf-8"

        class FakeResp:
            headers = FakeHeaders()

            def read(self):
                return page.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(req, timeout=25):
            seen["url"] = req.full_url
            return FakeResp()

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        fip_api.discover_gironi("RLO", "1DM", "2", "F")
        assert "codice_fase=2" in seen["url"]
        assert "sesso=F" in seen["url"]

    def test_fetch_failure_raises(self, monkeypatch):
        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda req, timeout=25: (_ for _ in ()).throw(
                                TimeoutError("down")))
        try:
            fip_api.discover_gironi("RLO", "1DM")
            assert False, "should have raised"
        except RuntimeError:
            pass
