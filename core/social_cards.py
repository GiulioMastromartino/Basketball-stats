"""Social PNG cards (Slice N3).

1080×1080 shareable graphics rendered with Pillow (no browser needed):
final-score cards and "Player of the game" cards. Served via the share
blueprint alongside the PDF exports and public ``/s/<token>`` links.
"""

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

SIZE = (1080, 1080)
BG = (18, 28, 38)
ACCENT = (232, 89, 12)
LIGHT = (242, 240, 232)
MUTED = (154, 160, 166)


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow without size kwarg
        return ImageFont.load_default()


def _base(draw_title: str):
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, SIZE[0], 28], fill=ACCENT)
    draw.rectangle([0, SIZE[1] - 28, SIZE[0], SIZE[1]], fill=ACCENT)
    draw.text((72, 84), draw_title, font=_font(48), fill=MUTED)
    return img, draw


def _centered(draw, y, text, font, fill=LIGHT):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    draw.text(((SIZE[0] - w) / 2, y), text, font=font, fill=fill)


def render_score_card(team_name: str, opponent: str, team_score: int,
                      opp_score: int, date: str = "", result: str = "") -> bytes:
    """Render a final-score card. Returns PNG bytes."""
    img, draw = _base("HOOPSLAB · FINAL SCORE")
    _centered(draw, 220, team_name or "Us", _font(72))
    _centered(draw, 320, f"{int(team_score or 0)} - {int(opp_score or 0)}",
              _font(200))
    _centered(draw, 560, f"vs {opponent or 'Opponent'}", _font(64))
    meta = " ".join(p for p in [date or "", result or ""] if p)
    if meta:
        _centered(draw, 660, meta, _font(48), fill=MUTED)
    _centered(draw, 900, "Generated with HoopsLab", _font(40), fill=MUTED)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_player_card(player_name: str, team_name: str = "",
                       stats: dict = None, date: str = "") -> bytes:
    """Render a "Player of the game" card. Returns PNG bytes."""
    stats = stats or {}
    img, draw = _base("HOOPSLAB · PLAYER OF THE GAME")
    _centered(draw, 220, player_name or "—", _font(88))
    if team_name:
        _centered(draw, 330, team_name, _font(48), fill=MUTED)
    pts = int(stats.get("points", 0) or 0)
    _centered(draw, 440, f"{pts} PTS", _font(170))
    line = (f"{int(stats.get('reb', 0) or 0)} REB · "
            f"{int(stats.get('ast', 0) or 0)} AST · "
            f"{int(stats.get('stl', 0) or 0)} STL · "
            f"{int(stats.get('blk', 0) or 0)} BLK")
    _centered(draw, 660, line, _font(52))
    if date:
        _centered(draw, 750, date, _font(44), fill=MUTED)
    _centered(draw, 900, "Generated with HoopsLab", _font(40), fill=MUTED)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
