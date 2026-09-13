"""Tests for the championship scraper adapters (offline fixtures)."""

from jobs.adapters import playbasket_html as pb


CALENDAR_HTML = """
<table><tr><th>Data</th><th>Casa</th><th>Ospite</th><th></th><th>PC</th><th>PO</th></tr>
<tr><td>16/10</td><td>Leone XIII Milano sq.B</td><td>Aurora Milano sq.B</td><td></td><td>68</td><td>60</td></tr>
<tr><td>17/10</td><td>Team X</td><td>Team Y</td><td></td><td></td><td></td></tr>
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
