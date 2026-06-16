from datetime import datetime

from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
bcrypt = Bcrypt()


class Organization(db.Model):
    __tablename__ = "organizations"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    teams = db.relationship("Team", backref="organization", lazy=True)
    memberships = db.relationship("OrganizationMembership", backref="organization", lazy=True)


class Team(db.Model):
    __tablename__ = "teams"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("organization_id", "slug"),)


class OrganizationMembership(db.Model):
    __tablename__ = "organization_memberships"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    is_gm = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "organization_id"),)


class TeamAssignment(db.Model):
    __tablename__ = "team_assignments"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    is_coach = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "team_id"),)
    team = db.relationship("Team", backref=db.backref("assignments", lazy=True))


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)

    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=True)

    workos_id = db.Column(db.String(255), unique=True, nullable=True)
    email_verified = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(20), nullable=False, default="editor")

    otp_code = db.Column(db.String(6), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)

    notification_channel = db.Column(
        db.String(20), nullable=False, default="email",
        server_default="email"
    )
    whatsapp_phone = db.Column(db.String(20), nullable=True)

    memberships = db.relationship("OrganizationMembership", backref="user", lazy=True)
    team_assignments = db.relationship("TeamAssignment", backref="user", lazy=True)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    @property
    def is_gm(self):
        mem = OrganizationMembership.query.filter_by(
            user_id=self.id, organization_id=self.organization_id, is_gm=True
        ).first()
        return mem is not None

    @property
    def is_coach(self):
        if not self.organization_id:
            return False
        from core.models import TeamAssignment
        ta = TeamAssignment.query.filter(
            TeamAssignment.user_id == self.id,
            TeamAssignment.is_coach == True,
        ).first()
        return ta is not None

    @property
    def is_admin(self):
        return self.is_gm

    @property
    def is_manager(self):
        return self.is_gm

    @property
    def assigned_teams(self):
        if self.is_gm:
            return Team.query.filter_by(organization_id=self.organization_id).all()
        return Team.query.join(TeamAssignment).filter(
            TeamAssignment.user_id == self.id
        ).all()


class SystemSetting(db.Model):
    __tablename__ = "system_settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=True)
    description = db.Column(db.String(255), nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=True)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    @classmethod
    def get_value(cls, key, default=None):
        setting = cls.query.filter_by(key=key).first()
        return setting.value if setting else default

    @classmethod
    def set_value(cls, key, value, description=None):
        setting = cls.query.filter_by(key=key).first()
        if not setting:
            setting = cls(key=key, value=value, description=description)
            db.session.add(setting)
        else:
            setting.value = value
            if description:
                setting.description = description
        db.session.commit()
        return setting


class Game(db.Model):
    __tablename__ = "games"
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    date = db.Column(db.String(10), nullable=False)
    opponent = db.Column(db.String(100), nullable=False)
    team_score = db.Column(db.Integer, nullable=False)
    opponent_score = db.Column(db.Integer, nullable=False)
    result = db.Column(db.String(1), nullable=False)
    game_type = db.Column(db.String(20), nullable=False)
    sort_date = db.Column(db.String(10), nullable=False)
    source = db.Column(db.String(20), default="IMPORT")
    schema_version = db.Column(db.Integer, default=1)

    team = db.relationship("Team", backref=db.backref("games", lazy=True))

    @property
    def score_display(self):
        return f"{self.team_score} - {self.opponent_score}"


class PlayerStat(db.Model):
    __tablename__ = "player_stats"
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    player_name = db.Column(db.String(100), nullable=False)
    points = db.Column(db.Integer, default=0)
    minutes = db.Column(db.String(10))
    reb = db.Column(db.Integer, default=0)
    ast = db.Column(db.Integer, default=0)
    fgm = db.Column(db.Integer, default=0)
    fga = db.Column(db.Integer, default=0)
    fg_percent = db.Column(db.Float, default=0)
    tpm = db.Column(db.Integer, default=0)
    tpa = db.Column(db.Integer, default=0)
    tp_percent = db.Column(db.Float, default=0)
    ftm = db.Column(db.Integer, default=0)
    fta = db.Column(db.Integer, default=0)
    ft_percent = db.Column(db.Float, default=0)
    oreb = db.Column(db.Integer, default=0)
    dreb = db.Column(db.Integer, default=0)
    stl = db.Column(db.Integer, default=0)
    blk = db.Column(db.Integer, default=0)
    tov = db.Column(db.Integer, default=0)
    pf = db.Column(db.Integer, default=0)
    plus_minus = db.Column(db.Integer, default=0)
    reb_conceded = db.Column(db.Integer, default=0)

    game = db.relationship("Game", backref=db.backref("stats", lazy=True))


class Play(db.Model):
    __tablename__ = "plays"
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    play_type = db.Column(db.String(50), default="Offense")
    source = db.Column(db.String(20), default="imported")
    image_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    canvas_data = db.Column(db.JSON, nullable=True)
    diagram_svg = db.Column(db.Text, nullable=True)
    difficulty = db.Column(db.String(20), server_default="Medium", nullable=False)
    personnel_required = db.Column(db.Text, nullable=True)
    tags = db.Column(db.Text, nullable=True)

    team = db.relationship("Team", backref=db.backref("plays", lazy=True))
    sequences = db.relationship("PlaySequence", backref="play", cascade="all, delete-orphan", lazy=True)


class PlaySequence(db.Model):
    __tablename__ = "play_sequences"
    id = db.Column(db.Integer, primary_key=True)
    play_id = db.Column(db.Integer, db.ForeignKey("plays.id"), nullable=False)
    sequence_number = db.Column(db.Integer, nullable=False)
    element_data = db.Column(db.JSON, nullable=True)
    caption = db.Column(db.String(255), nullable=True)


class PlayType(db.Model):
    __tablename__ = "play_types"
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    name = db.Column(db.String(50), unique=True, nullable=False)

    team = db.relationship("Team", backref=db.backref("play_types", lazy=True))


class ShotEvent(db.Model):
    __tablename__ = "shot_events"
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    player_name = db.Column(db.String(100))
    shot_type = db.Column(db.String(10))
    result = db.Column(db.String(10))
    points = db.Column(db.Integer, default=0)
    x_loc = db.Column(db.Float, nullable=True)
    y_loc = db.Column(db.Float, nullable=True)
    zone = db.Column(db.String(50), nullable=True)
    quarter = db.Column(db.Integer)
    play_id = db.Column(db.Integer, db.ForeignKey("plays.id"), nullable=True)

    game = db.relationship("Game", backref=db.backref("shots", lazy=True))
    play = db.relationship("Play", backref=db.backref("shot_events", lazy=True))


class GameEvent(db.Model):
    __tablename__ = "game_events"
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    event_type = db.Column(db.String(50))
    player_name = db.Column(db.String(100), nullable=True)
    detail = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.BigInteger, default=0)
    shot_attempt = db.Column(db.String(10), nullable=True)
    play_id = db.Column(db.Integer, db.ForeignKey("plays.id"), nullable=True)
    quarter = db.Column(db.Integer, nullable=True)
    time_remaining = db.Column(db.String(10), nullable=True)
    score_margin = db.Column(db.Integer, nullable=True)
    possession_number = db.Column(db.Integer, nullable=True)
    game_seconds = db.Column(db.Integer, nullable=True)
    x_loc = db.Column(db.Float, nullable=True)
    y_loc = db.Column(db.Float, nullable=True)
    zone = db.Column(db.String(50), nullable=True)
    lineup_segment_id = db.Column(db.Integer, db.ForeignKey("lineup_segments.id"), nullable=True)

    game = db.relationship("Game", backref=db.backref("events", lazy=True))
    play = db.relationship("Play", backref=db.backref("game_events", lazy=True))
    lineup_segment = db.relationship("LineupSegment", backref=db.backref("events", lazy=True))


class LineupSegment(db.Model):
    """Tracks exactly which 5 players are on the floor at every moment"""

    __tablename__ = "lineup_segments"
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    start_timestamp = db.Column(db.BigInteger, nullable=False)
    end_timestamp = db.Column(db.BigInteger, nullable=True)
    quarter = db.Column(db.Integer, nullable=True)
    players = db.Column(db.JSON, nullable=False)
    lineup_hash = db.Column(db.String(64), nullable=False)

    points_scored = db.Column(db.Integer, default=0)
    points_allowed = db.Column(db.Integer, default=0)
    possessions = db.Column(db.Integer, default=0)
    reb_conceded = db.Column(db.Integer, default=0)
    duration_seconds = db.Column(db.Integer, default=0)
    lineup_id = db.Column(db.Integer, db.ForeignKey("lineups.id"), nullable=True)

    game = db.relationship("Game", backref=db.backref("lineup_segments", lazy=True))


class Lineup(db.Model):
    """Multi-game lineup tracking with cached stats"""

    __tablename__ = "lineups"
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    lineup_hash = db.Column(db.String(64), unique=True, nullable=False)
    players = db.Column(db.JSON, nullable=False)
    display_name = db.Column(db.String(100), nullable=True)
    is_starting = db.Column(db.Boolean, default=False)

    total_seconds = db.Column(db.Integer, default=0)
    total_possessions = db.Column(db.Integer, default=0)
    points_scored = db.Column(db.Integer, default=0)
    points_allowed = db.Column(db.Integer, default=0)
    games_played = db.Column(db.Integer, default=0)
    segment_count = db.Column(db.Integer, default=0)

    ortg = db.Column(db.Float, default=0)
    drtg = db.Column(db.Float, default=0)
    net_rating = db.Column(db.Float, default=0)

    fgm = db.Column(db.Integer, default=0)
    fga = db.Column(db.Integer, default=0)
    tpm = db.Column(db.Integer, default=0)
    tpa = db.Column(db.Integer, default=0)
    ftm = db.Column(db.Integer, default=0)
    fta = db.Column(db.Integer, default=0)
    oreb = db.Column(db.Integer, default=0)
    dreb = db.Column(db.Integer, default=0)
    ast = db.Column(db.Integer, default=0)
    stl = db.Column(db.Integer, default=0)
    blk = db.Column(db.Integer, default=0)
    tov = db.Column(db.Integer, default=0)
    reb_conceded = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    team = db.relationship("Team", backref=db.backref("lineups", lazy=True))
    segments = db.relationship("LineupSegment", backref="lineup_ref", lazy=True)


class Possession(db.Model):
    """Distinct possession tracking for pace-adjusted stats"""

    __tablename__ = "possessions"
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    start_event_id = db.Column(db.Integer, db.ForeignKey("game_events.id"), nullable=False)
    end_event_id = db.Column(db.Integer, db.ForeignKey("game_events.id"), nullable=True)
    team_possession = db.Column(db.Boolean, default=True)
    quarter = db.Column(db.Integer, nullable=True)
    points = db.Column(db.Integer, default=0)
    play_id = db.Column(db.Integer, db.ForeignKey("plays.id"), nullable=True)

    game = db.relationship("Game", backref=db.backref("possessions", lazy=True))
    start_event = db.relationship("GameEvent", foreign_keys=[start_event_id])
    end_event = db.relationship("GameEvent", foreign_keys=[end_event_id])
    play = db.relationship("Play", backref=db.backref("possessions", lazy=True))


class ShotZone(db.Model):
    """Expected point values for different court zones"""

    __tablename__ = "shot_zones"
    id = db.Column(db.Integer, primary_key=True)
    zone_name = db.Column(db.String(50), unique=True, nullable=False)
    zone_type = db.Column(db.String(20), nullable=False)
    expected_value = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    x_min = db.Column(db.Float, nullable=True)
    x_max = db.Column(db.Float, nullable=True)
    y_min = db.Column(db.Float, nullable=True)
    y_max = db.Column(db.Float, nullable=True)


class PlayerLineupStats(db.Model):
    """Aggregated stats for a player during a specific lineup segment"""

    __tablename__ = "player_lineup_stats"
    id = db.Column(db.Integer, primary_key=True)
    lineup_segment_id = db.Column(db.Integer, db.ForeignKey("lineup_segments.id"), nullable=False)
    player_name = db.Column(db.String(100), nullable=False)

    points = db.Column(db.Integer, default=0)
    fga = db.Column(db.Integer, default=0)
    fgm = db.Column(db.Integer, default=0)
    tpa = db.Column(db.Integer, default=0)
    tpm = db.Column(db.Integer, default=0)
    fta = db.Column(db.Integer, default=0)
    ftm = db.Column(db.Integer, default=0)
    oreb = db.Column(db.Integer, default=0)
    dreb = db.Column(db.Integer, default=0)
    ast = db.Column(db.Integer, default=0)
    stl = db.Column(db.Integer, default=0)
    blk = db.Column(db.Integer, default=0)
    tov = db.Column(db.Integer, default=0)
    reb_conceded = db.Column(db.Integer, default=0)

    lineup_segment = db.relationship("LineupSegment", backref=db.backref("player_stats", lazy=True))


class WhatsAppGroup(db.Model):
    """WhatsApp groups registered per team for broadcasting notifications."""

    __tablename__ = "whatsapp_groups"
    id          = db.Column(db.Integer, primary_key=True)
    team_id     = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    group_name  = db.Column(db.String(100), nullable=False)
    group_wa_id = db.Column(db.String(50), nullable=False)
    active      = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    team = db.relationship("Team", backref=db.backref("whatsapp_groups", lazy=True))


class Player(db.Model):
    """Player model for managing player information and performance reports"""

    __tablename__ = "players"
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    name = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    active = db.Column(db.Boolean, default=True, server_default="1", nullable=False)
    notification_channel = db.Column(
        db.String(20), nullable=False, default="email",
        server_default="email"
    )
    whatsapp_phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    team = db.relationship("Team", backref=db.backref("players", lazy=True))

    def __repr__(self):
        return f"<Player {self.name}>"
