"""Export and import of whole organizations as portable JSON bundles.

The Admin panel uses this to move an organization between deployments (or
to take a backup) without touching user accounts. An export contains the
organization plus every team-scoped row the app owns: seasons, players,
games, stat lines, shot/event logs, lineups, plays, training sessions,
tracked championships, WhatsApp groups and development goals.

Deliberately **not** exported:

* users, memberships and team assignments (accounts are deployment-local
  and passwords must never travel in a backup file),
* admin audit rows (they describe local actions),
* share links (their tokens are live credentials),
* system settings (keys are global, not per-org).

An import always creates a *new* organization. It never merges into or
overwrites an existing one; name collisions get a unique suffix instead.
"""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import DateTime

from core.models import (
    DevelopmentGoal,
    Game,
    GameEvent,
    Lineup,
    LineupSegment,
    Organization,
    OrganizationMembership,
    Player,
    PlayerLineupStats,
    PlayerStat,
    Play,
    PlaySequence,
    PlayType,
    Possession,
    Season,
    ShotEvent,
    Team,
    TrackedChampionship,
    TrainingAttendance,
    TrainingSegment,
    TrainingSegmentTemplate,
    TrainingSession,
    WhatsAppGroup,
    db,
)

EXPORT_FORMAT = "hoopslab.organizations"
EXPORT_VERSION = 1


class OrgImportError(ValueError):
    """Raised when an organization bundle cannot be imported safely."""


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _dump(model, obj, *, exclude=()):
    """Serialize one row to a JSON-safe dict (id kept for remapping)."""
    row = {"id": obj.id}
    for column in model.__table__.columns:
        name = column.name
        if name == "id" or name in exclude:
            continue
        value = getattr(obj, name)
        if isinstance(value, datetime):
            value = value.isoformat()
        row[name] = value
    return row


def export_organizations(org_ids):
    """Return a bundle dict for the given organization ids."""
    orgs = (
        Organization.query.filter(Organization.id.in_(list(org_ids)))
        .order_by(Organization.name, Organization.id)
        .all()
    )
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "organizations": [_export_org(org) for org in orgs],
    }


def _export_org(org):
    teams = (
        Team.query.filter_by(organization_id=org.id)
        .order_by(Team.name, Team.id)
        .all()
    )
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "timezone": org.timezone,
        "sport": org.sport,
        "season_convention": org.season_convention,
        "created_at": org.created_at.isoformat() if org.created_at else None,
        "teams": [_export_team(team) for team in teams],
    }


def _export_team(team):
    seasons = (
        Season.query.filter_by(team_id=team.id)
        .order_by(Season.start_date, Season.id)
        .all()
    )
    players = Player.query.filter_by(team_id=team.id).order_by(Player.name).all()
    plays = (
        Play.query.filter_by(team_id=team.id).order_by(Play.name, Play.id).all()
    )
    games = (
        Game.query.filter_by(team_id=team.id)
        .order_by(Game.sort_date, Game.id)
        .all()
    )
    sessions = (
        TrainingSession.query.filter_by(team_id=team.id)
        .order_by(TrainingSession.session_date, TrainingSession.id)
        .all()
    )
    lineups = (
        Lineup.query.filter_by(team_id=team.id)
        .order_by(Lineup.lineup_hash, Lineup.id)
        .all()
    )
    return {
        "id": team.id,
        "name": team.name,
        "slug": team.slug,
        "created_at": team.created_at.isoformat() if team.created_at else None,
        "seasons": [_dump(Season, season) for season in seasons],
        "players": [_dump(Player, player) for player in players],
        "plays": [_export_play(play) for play in plays],
        "play_types": [_dump(PlayType, play_type) for play_type in (
            PlayType.query.filter_by(team_id=team.id).order_by(PlayType.name).all()
        )],
        "lineups": [_dump(Lineup, lineup) for lineup in lineups],
        "games": [_export_game(game) for game in games],
        "training_sessions": [_export_training_session(s) for s in sessions],
        "training_segment_templates": [
            _dump(TrainingSegmentTemplate, template) for template in (
                TrainingSegmentTemplate.query.filter_by(team_id=team.id)
                .order_by(TrainingSegmentTemplate.title).all()
            )
        ],
        "tracked_championships": [
            _dump(TrackedChampionship, tracked) for tracked in (
                TrackedChampionship.query.filter_by(team_id=team.id)
                .order_by(TrackedChampionship.id).all()
            )
        ],
        "whatsapp_groups": [
            _dump(WhatsAppGroup, group) for group in (
                WhatsAppGroup.query.filter_by(team_id=team.id)
                .order_by(WhatsAppGroup.group_name).all()
            )
        ],
        "development_goals": [
            _dump(DevelopmentGoal, goal) for goal in (
                DevelopmentGoal.query.filter_by(team_id=team.id)
                .order_by(DevelopmentGoal.id).all()
            )
        ],
    }


def _export_play(play):
    data = _dump(Play, play)
    data["sequences"] = [
        _dump(PlaySequence, sequence) for sequence in (
            PlaySequence.query.filter_by(play_id=play.id)
            .order_by(PlaySequence.sequence_number, PlaySequence.id).all()
        )
    ]
    return data


def _export_game(game):
    data = _dump(Game, game)
    data["player_stats"] = [
        _dump(PlayerStat, row) for row in (
            PlayerStat.query.filter_by(game_id=game.id)
            .order_by(PlayerStat.id).all()
        )
    ]
    data["events"] = [
        _dump(GameEvent, row) for row in (
            GameEvent.query.filter_by(game_id=game.id)
            .order_by(GameEvent.timestamp, GameEvent.id).all()
        )
    ]
    data["shots"] = [
        _dump(ShotEvent, row) for row in (
            ShotEvent.query.filter_by(game_id=game.id)
            .order_by(ShotEvent.id).all()
        )
    ]
    segments = (
        LineupSegment.query.filter_by(game_id=game.id)
        .order_by(LineupSegment.start_timestamp, LineupSegment.id)
        .all()
    )
    data["lineup_segments"] = []
    for segment in segments:
        segment_data = _dump(LineupSegment, segment)
        segment_data["player_stats"] = [
            _dump(PlayerLineupStats, row) for row in (
                PlayerLineupStats.query.filter_by(lineup_segment_id=segment.id)
                .order_by(PlayerLineupStats.id).all()
            )
        ]
        data["lineup_segments"].append(segment_data)
    data["possessions"] = [
        _dump(Possession, row) for row in (
            Possession.query.filter_by(game_id=game.id)
            .order_by(Possession.id).all()
        )
    ]
    return data


def _export_training_session(session):
    data = _dump(TrainingSession, session)
    data["segments"] = [
        _dump(TrainingSegment, row) for row in (
            TrainingSegment.query.filter_by(session_id=session.id)
            .order_by(TrainingSegment.position, TrainingSegment.id).all()
        )
    ]
    data["attendance"] = [
        _dump(TrainingAttendance, row) for row in (
            TrainingAttendance.query.filter_by(session_id=session.id)
            .order_by(TrainingAttendance.id).all()
        )
    ]
    return data


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------


def _parse_datetime(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            raise OrgImportError(f"invalid timestamp: {value!r}")
    # Columns are naive UTC; drop any offset the exporter added.
    return dt.replace(tzinfo=None)


def _values(model, row, *, exclude=(), overrides=None):
    """Copy known columns from a bundle row, converting timestamps."""
    columns = {column.name: column for column in model.__table__.columns}
    data = {}
    for key, value in row.items():
        if key in ("id",) or key in exclude or key not in columns:
            continue
        column = columns[key]
        if isinstance(column.type, DateTime):
            value = _parse_datetime(value)
        data[key] = value
    if overrides:
        data.update(overrides)
    return data


def _build(model, row, *, exclude=(), overrides=None):
    obj = model(**_values(model, row, exclude=exclude, overrides=overrides))
    db.session.add(obj)
    return obj


def _rows(parent, key, label):
    value = parent.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise OrgImportError(f"{label}.{key} must be a list of objects")
    return value


def _old_id(row, label):
    value = row.get("id")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise OrgImportError(f"{label} has an invalid id: {value!r}")


def _slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug or "unnamed"


def _unique_org_slug(base):
    base = _slugify(base)[:50]
    candidate = base
    n = 2
    while Organization.query.filter_by(slug=candidate).first():
        suffix = f"-{n}"
        candidate = base[: 50 - len(suffix)] + suffix
        n += 1
    return candidate


def _unique_by(base, exists, *, limit=100, suffix=" (imported)"):
    base = str(base or "").strip()[:limit] or "Untitled"
    if not exists(base):
        return base
    candidate = base[: limit - len(suffix)] + suffix
    if not exists(candidate):
        return candidate
    n = 2
    while True:
        tail = f"{suffix} {n}"
        candidate = base[: limit - len(tail)] + tail
        if not exists(candidate):
            return candidate
        n += 1


def _unique_player_name(base):
    return _unique_by(
        base, lambda name: Player.query.filter_by(name=name).first() is not None
    )


def _unique_play_name(base):
    return _unique_by(
        base, lambda name: Play.query.filter_by(name=name).first() is not None
    )


def _unique_team_slug(org_id, base):
    base = _slugify(base)[:50]
    candidate = base
    n = 2
    while Team.query.filter_by(organization_id=org_id, slug=candidate).first():
        suffix = f"-{n}"
        candidate = base[: 50 - len(suffix)] + suffix
        n += 1
    return candidate


def _unique_season_name(team_id, base, seen):
    def exists(name):
        return name in seen or Season.query.filter_by(
            team_id=team_id, name=name
        ).first() is not None

    name = _unique_by(base, exists, limit=50)
    seen.add(name)
    return name


def _bool(value, default=False):
    if value is None:
        return default
    return bool(value)


def _str(value, default=""):
    return default if value is None else str(value)


def _map_player_name(value, name_map):
    return name_map.get(value, value) if isinstance(value, str) else value


def _remap_player_names(obj, name_map):
    """Point name-keyed rows at a player that was renamed during import.

    ``Player.name`` is globally unique, so a colliding player becomes
    ``"<name> (imported)"``. Stats, events, shots, lineup player lists and
    development goals keep the *old* name unless they are remapped here;
    without this they would no longer identify the imported roster player.
    """
    if not name_map:
        return obj
    value = getattr(obj, "player_name", None)
    if isinstance(value, str) and value in name_map:
        obj.player_name = name_map[value]
    players = getattr(obj, "players", None)
    if isinstance(players, list):
        obj.players = [_map_player_name(item, name_map) for item in players]
    return obj


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def _validate_bundle(payload):
    if not isinstance(payload, dict):
        raise OrgImportError("file must contain a JSON object")
    if payload.get("format") != EXPORT_FORMAT:
        raise OrgImportError(
            f"unsupported file format (expected '{EXPORT_FORMAT}')"
        )
    if payload.get("version") != EXPORT_VERSION:
        raise OrgImportError(
            f"unsupported export version {payload.get('version')!r} "
            f"(this server reads version {EXPORT_VERSION})"
        )
    orgs = payload.get("organizations")
    if not isinstance(orgs, list) or not orgs:
        raise OrgImportError("bundle contains no organizations")
    if not all(isinstance(org, dict) for org in orgs):
        raise OrgImportError("'organizations' must be a list of objects")


def import_organizations(payload, *, actor=None, add_membership=True):
    """Import a bundle, returning ``(organizations, warnings)``.

    Everything is committed as one transaction: on any error the session is
    rolled back and nothing is left behind.
    """
    _validate_bundle(payload)
    warnings = []
    imported = []
    try:
        for raw_org in payload["organizations"]:
            imported.append(
                _import_org(raw_org, actor=actor,
                            add_membership=add_membership, warnings=warnings)
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return imported, warnings


def _import_org(raw_org, *, actor, add_membership, warnings):
    name = _str(raw_org.get("name")).strip()[:100]
    if not name:
        raise OrgImportError("an organization is missing its name")

    convention = _str(raw_org.get("season_convention"), "sept-june").strip()
    if convention not in ("sept-june", "calendar"):
        convention = "sept-june"

    org = Organization(
        name=name,
        slug=_unique_org_slug(raw_org.get("slug") or name),
        timezone=_str(raw_org.get("timezone"), "UTC").strip()[:50] or "UTC",
        sport=_str(raw_org.get("sport"), "basketball").strip()[:50] or "basketball",
        season_convention=convention,
    )
    db.session.add(org)
    db.session.flush()

    if add_membership and actor is not None and getattr(actor, "id", 0):
        db.session.add(OrganizationMembership(
            user_id=actor.id, organization_id=org.id, is_gm=True
        ))

    for raw_team in _rows(raw_org, "teams", f"organization '{name}'"):
        _import_team(org, raw_team, warnings)

    return org


def _import_team(org, raw_team, warnings):
    team_name = _str(raw_team.get("name")).strip()[:100] or "Imported team"
    team = Team(
        organization_id=org.id,
        name=team_name,
        slug=_unique_team_slug(
            org.id, raw_team.get("slug") or team_name
        ),
    )
    db.session.add(team)
    db.session.flush()

    label = f"team '{team.name}'"

    # Seasons.
    season_map = {}
    seen_seasons = set()
    for row in _rows(raw_team, "seasons", label):
        season = _build(
            Season, row,
            exclude=("team_id",),
            overrides={
                "team_id": team.id,
                "name": _unique_season_name(
                    team.id, _str(row.get("name")).strip() or "Season",
                    seen_seasons,
                ),
                "start_date": _str(row.get("start_date")).strip()[:10],
                "end_date": _str(row.get("end_date")).strip()[:10],
                "is_active": _bool(row.get("is_active")),
            },
        )
        season_map[_old_id(row, "season")] = season
    db.session.flush()

    # Players. Player.name is globally unique, so clashes get a suffix.
    player_map = {}
    player_name_map = {}
    for row in _rows(raw_team, "players", label):
        name = _str(row.get("name")).strip()
        if not name:
            warnings.append(f"Skipped an unnamed player in {label}.")
            continue
        email = _str(row.get("email")).strip() or None
        if email and Player.query.filter_by(email=email).first():
            warnings.append(
                f"Cleared duplicate player email '{email}' "
                f"for '{name}' in {label}."
            )
            email = None
        player = _build(
            Player, row,
            exclude=("team_id", "name"),
            overrides={
                "team_id": team.id,
                "name": _unique_player_name(name),
                "email": email,
            },
        )
        player_map[_old_id(row, "player")] = player
        if player.name != name:
            player_name_map[name] = player.name
    db.session.flush()

    # Plays (global unique name) and their storyboard sequences.
    play_map = {}
    for row in _rows(raw_team, "plays", label):
        play_name = _str(row.get("name")).strip() or "Untitled play"
        play = _build(
            Play, row,
            exclude=("team_id", "name", "sequences"),
            overrides={
                "team_id": team.id,
                "name": _unique_play_name(play_name),
            },
        )
        play_map[_old_id(row, "play")] = play
        db.session.flush()
        for sequence_row in _rows(row, "sequences", f"play '{play_name}'"):
            _build(
                PlaySequence, sequence_row,
                exclude=("play_id",),
                overrides={"play_id": play.id},
            )
    db.session.flush()

    # Play types carry a global unique name; reuse an existing one.
    for row in _rows(raw_team, "play_types", label):
        play_type_name = _str(row.get("name")).strip()[:50]
        if not play_type_name:
            continue
        if PlayType.query.filter_by(name=play_type_name).first():
            warnings.append(
                f"Kept the existing play type '{play_type_name}' "
                f"(same name already exists)."
            )
            continue
        _build(
            PlayType, row,
            exclude=("team_id", "name"),
            overrides={"team_id": team.id, "name": play_type_name},
        )
    db.session.flush()

    # Multi-game lineups (segments reference these).
    lineup_map = {}
    seen_lineup_hashes = set()
    for row in _rows(raw_team, "lineups", label):
        lineup_hash = _str(row.get("lineup_hash")).strip()
        if not lineup_hash:
            warnings.append(f"Skipped a lineup without a hash in {label}.")
            continue
        if lineup_hash in seen_lineup_hashes:
            warnings.append(
                f"Skipped duplicate lineup '{lineup_hash}' in {label}."
            )
            continue
        seen_lineup_hashes.add(lineup_hash)
        lineup = _build(
            Lineup, row,
            exclude=("team_id",),
            overrides={"team_id": team.id},
        )
        _remap_player_names(lineup, player_name_map)
        lineup_map[_old_id(row, "lineup")] = lineup
    db.session.flush()

    for game_row in _rows(raw_team, "games", label):
        _import_game(
            team, game_row, season_map=season_map, play_map=play_map,
            lineup_map=lineup_map, player_name_map=player_name_map,
            warnings=warnings,
        )

    for session_row in _rows(raw_team, "training_sessions", label):
        _import_training_session(
            team, session_row, player_map=player_map, play_map=play_map,
            label=label, warnings=warnings,
        )

    seen_templates = set()
    for row in _rows(raw_team, "training_segment_templates", label):
        title = _str(row.get("title")).strip()[:150]
        if not title:
            continue
        if title in seen_templates:
            warnings.append(
                f"Skipped duplicate training template '{title}' in {label}."
            )
            continue
        seen_templates.add(title)
        _build(
            TrainingSegmentTemplate, row,
            exclude=("team_id", "title", "play_id"),
            overrides={
                "team_id": team.id,
                "title": title,
                "play_id": _mapped_id(play_map, row.get("play_id")),
            },
        )

    seen_tracked = set()
    for row in _rows(raw_team, "tracked_championships", label):
        key = tuple(
            _str(row.get(field))
            for field in (
                "provider", "comitato_codice", "province_codice",
                "codice_campionato", "codice_fase", "codice_girone",
                "season_label",
            )
        )
        if key in seen_tracked:
            continue
        seen_tracked.add(key)
        _build(
            TrackedChampionship, row,
            exclude=("team_id",),
            overrides={"team_id": team.id},
        )

    for row in _rows(raw_team, "whatsapp_groups", label):
        _build(
            WhatsAppGroup, row,
            exclude=("team_id",),
            overrides={"team_id": team.id},
        )

    for row in _rows(raw_team, "development_goals", label):
        goal = _build(
            DevelopmentGoal, row,
            exclude=("team_id",),
            overrides={"team_id": team.id},
        )
        _remap_player_names(goal, player_name_map)

    db.session.flush()


def _mapped(mapping, old_id):
    try:
        return mapping.get(int(old_id)) if old_id is not None else None
    except (TypeError, ValueError):
        return None


def _mapped_id(mapping, old_id):
    obj = _mapped(mapping, old_id)
    return obj.id if obj is not None else None


def _import_game(team, raw_game, *, season_map, play_map, lineup_map,
                 player_name_map, warnings):
    label = f"game '{_str(raw_game.get('opponent'), '?')}'"
    game = _build(
        Game, raw_game,
        exclude=("team_id", "season_id", "player_stats", "events", "shots",
                 "lineup_segments", "possessions"),
        overrides={
            "team_id": team.id,
            "season_id": _mapped_id(season_map, raw_game.get("season_id")),
        },
    )
    db.session.flush()

    for row in _rows(raw_game, "player_stats", label):
        stat = _build(
            PlayerStat, row,
            exclude=("game_id",),
            overrides={"game_id": game.id},
        )
        _remap_player_names(stat, player_name_map)

    # Events first (their lineup_segment_id is linked after segments exist).
    event_map = {}
    pending_event_segments = []
    for row in _rows(raw_game, "events", label):
        event = _build(
            GameEvent, row,
            exclude=("game_id", "play_id", "lineup_segment_id"),
            overrides={
                "game_id": game.id,
                "play_id": _mapped_id(play_map, row.get("play_id")),
            },
        )
        _remap_player_names(event, player_name_map)
        event_map[_old_id(row, "event")] = event
        if row.get("lineup_segment_id") is not None:
            pending_event_segments.append(
                (event, row.get("lineup_segment_id"))
            )

    for row in _rows(raw_game, "shots", label):
        shot = _build(
            ShotEvent, row,
            exclude=("game_id", "play_id"),
            overrides={
                "game_id": game.id,
                "play_id": _mapped_id(play_map, row.get("play_id")),
            },
        )
        _remap_player_names(shot, player_name_map)

    segment_map = {}
    for row in _rows(raw_game, "lineup_segments", label):
        segment = _build(
            LineupSegment, row,
            exclude=("game_id", "lineup_id", "player_stats"),
            overrides={
                "game_id": game.id,
                "lineup_id": _mapped_id(lineup_map, row.get("lineup_id")),
            },
        )
        _remap_player_names(segment, player_name_map)
        segment_map[_old_id(row, "segment")] = segment
        db.session.flush()
        for stat_row in _rows(row, "player_stats", f"{label} segment"):
            lineup_stat = _build(
                PlayerLineupStats, stat_row,
                exclude=("lineup_segment_id",),
                overrides={"lineup_segment_id": segment.id},
            )
            _remap_player_names(lineup_stat, player_name_map)

    for event, old_segment_id in pending_event_segments:
        segment = _mapped(segment_map, old_segment_id)
        if segment is None:
            warnings.append(
                f"Dropped a {label} event link to a missing lineup segment."
            )
        event.lineup_segment_id = segment.id if segment is not None else None

    # A game with events and possessions but no lineup segments never hits the
    # per-segment flush above, so assign the event ids before the possession
    # rows copy ``start_event_id`` (nullable=False) from them.
    db.session.flush()

    for row in _rows(raw_game, "possessions", label):
        start_event = _mapped(event_map, row.get("start_event_id"))
        if start_event is None:
            warnings.append(f"Skipped a possession in {label} without its start event.")
            continue
        end_event = _mapped(event_map, row.get("end_event_id"))
        _build(
            Possession, row,
            exclude=("game_id", "start_event_id", "end_event_id", "play_id"),
            overrides={
                "game_id": game.id,
                "start_event_id": start_event.id,
                "end_event_id": end_event.id if end_event is not None else None,
                "play_id": _mapped_id(play_map, row.get("play_id")),
            },
        )

    db.session.flush()


def _import_training_session(team, raw_session, *, player_map, play_map,
                             label, warnings):
    session = _build(
        TrainingSession, raw_session,
        exclude=("team_id", "segments", "attendance"),
        overrides={"team_id": team.id},
    )
    db.session.flush()

    for row in _rows(raw_session, "segments", f"training session in {label}"):
        _build(
            TrainingSegment, row,
            exclude=("session_id", "play_id"),
            overrides={
                "session_id": session.id,
                "play_id": _mapped_id(play_map, row.get("play_id")),
            },
        )

    seen_players = set()
    for row in _rows(raw_session, "attendance", f"training session in {label}"):
        player = _mapped(player_map, row.get("player_id"))
        if player is None:
            warnings.append(
                f"Dropped attendance for an unknown player in {label}."
            )
            continue
        if player.id in seen_players:
            continue
        seen_players.add(player.id)
        _build(
            TrainingAttendance, row,
            exclude=("session_id", "player_id"),
            overrides={"session_id": session.id, "player_id": player.id},
        )

    db.session.flush()
