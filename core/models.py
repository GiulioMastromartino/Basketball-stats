from datetime import datetime

from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
bcrypt = Bcrypt()


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    # New Role Field
    # Options: 'admin', 'editor', 'viewer'
    role = db.Column(db.String(20), nullable=False, default="editor")

    # Deprecated but kept for safety during migration
    is_admin = db.Column(db.Boolean, default=False)

    # OTP Fields
    otp_code = db.Column(db.String(6), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    @property
    def is_manager(self):
        """Check if user has admin privileges (supports legacy check)"""
        return self.role == "admin" or self.is_admin


class SystemSetting(db.Model):
    __tablename__ = "system_settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=True)
    description = db.Column(db.String(255), nullable=True)
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
    date = db.Column(db.String(10), nullable=False)
    opponent = db.Column(db.String(100), nullable=False)
    team_score = db.Column(db.Integer, nullable=False)
    opponent_score = db.Column(db.Integer, nullable=False)
    result = db.Column(db.String(1), nullable=False)
    game_type = db.Column(db.String(20), nullable=False)
    sort_date = db.Column(db.String(10), nullable=False)
    source = db.Column(db.String(20), default="IMPORT")  # LIVE, IMPORT, MANUAL

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
    plus_minus = db.Column(db.Integer, default=0)  # +/- Stat
    reb_conceded = db.Column(db.Integer, default=0)  # Offensive rebounds conceded to opponents

    # Relationship to Game
    game = db.relationship("Game", backref=db.backref("stats", lazy=True))


class Play(db.Model):
    __tablename__ = "plays"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    play_type = db.Column(db.String(50), default="Offense")  # Offense, Defense, Special
    image_filename = db.Column(
        db.String(255), nullable=True
    )  # Stored in uploads/plays/
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Phase 1 fields for Builder
    canvas_data = db.Column(db.JSON, nullable=True)  # Fabric.js JSON (Source of Truth)
    diagram_svg = db.Column(db.Text, nullable=True)  # Server-rendered SVG
    difficulty = db.Column(db.String(20), server_default="Medium", nullable=False)
    personnel_required = db.Column(db.Text, nullable=True)
    tags = db.Column(db.Text, nullable=True)

    # Relationship to sequences
    sequences = db.relationship(
        "PlaySequence", backref="play", cascade="all, delete-orphan", lazy=True
    )


class PlaySequence(db.Model):
    __tablename__ = "play_sequences"
    id = db.Column(db.Integer, primary_key=True)
    play_id = db.Column(db.Integer, db.ForeignKey("plays.id"), nullable=False)
    sequence_number = db.Column(db.Integer, nullable=False)
    element_data = db.Column(
        db.JSON, nullable=True
    )  # Full snapshot for animation frame
    caption = db.Column(db.String(255), nullable=True)


class PlayType(db.Model):
    __tablename__ = "play_types"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


class ShotEvent(db.Model):
    __tablename__ = "shot_events"
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    player_name = db.Column(db.String(100))
    shot_type = db.Column(db.String(10))  # 2pt, 3pt, ft
    result = db.Column(db.String(10))  # made, missed
    points = db.Column(db.Integer, default=0)
    x_loc = db.Column(db.Float, nullable=True)  # Normalized 0-500
    y_loc = db.Column(db.Float, nullable=True)  # Normalized 0-470
    quarter = db.Column(db.Integer)
    play_id = db.Column(
        db.Integer, db.ForeignKey("plays.id"), nullable=True
    )  # Tagged play

    game = db.relationship("Game", backref=db.backref("shots", lazy=True))
    play = db.relationship("Play", backref=db.backref("shot_events", lazy=True))


class GameEvent(db.Model):
    __tablename__ = "game_events"
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    event_type = db.Column(
        db.String(50)
    )  # SHOT_2PT, SHOT_3PT, TURNOVER, SUB_IN, SUB_OUT, OPP_SCORE, FT, OPP_OREB, FT_MADE, FT_MISS
    player_name = db.Column(db.String(100), nullable=True)
    detail = db.Column(
        db.String(255), nullable=True
    )  # e.g. amount of points for opp score
    timestamp = db.Column(db.BigInteger, default=0)  # generic ordering index
    shot_attempt = db.Column(
        db.String(10), nullable=True
    )  # 'attempted' or 'made' for shots
    play_id = db.Column(
        db.Integer, db.ForeignKey("plays.id"), nullable=True
    )  # Tagged play
    quarter = db.Column(db.Integer, nullable=True)  # Quarter period (1-4, OT)
    time_remaining = db.Column(db.String(10), nullable=True)  # MM:SS format
    score_margin = db.Column(
        db.Integer, nullable=True
    )  # Point differential at event time
    possession_number = db.Column(
        db.Integer, nullable=True
    )  # Possession sequence number
    game_seconds = db.Column(db.Integer, nullable=True)  # Absolute game time in seconds
    lineup_segment_id = db.Column(
        db.Integer, db.ForeignKey("lineup_segments.id"), nullable=True
    )  # Link to active lineup during this event

    game = db.relationship("Game", backref=db.backref("events", lazy=True))
    play = db.relationship("Play", backref=db.backref("game_events", lazy=True))
    lineup_segment = db.relationship(
        "LineupSegment", backref=db.backref("events", lazy=True)
    )


class LineupSegment(db.Model):
    """Tracks exactly which 5 players are on the floor at every moment"""

    __tablename__ = "lineup_segments"
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    start_timestamp = db.Column(
        db.BigInteger, nullable=False
    )  # Event index when segment starts
    end_timestamp = db.Column(
        db.BigInteger, nullable=True
    )  # Event index when segment ends (NULL = current)
    quarter = db.Column(db.Integer, nullable=True)
    players = db.Column(
        db.JSON, nullable=False
    )  # List of 5 player names ["Player1", "Player2", ...]
    lineup_hash = db.Column(
        db.String(64), nullable=False
    )  # MD5 hash of sorted player names for quick lookup

    # Stats during this segment
    points_scored = db.Column(db.Integer, default=0)
    points_allowed = db.Column(db.Integer, default=0)
    possessions = db.Column(db.Integer, default=0)
    duration_seconds = db.Column(db.Integer, default=0)  # Actual playing time in seconds
    lineup_id = db.Column(db.Integer, db.ForeignKey("lineups.id"), nullable=True)  # Link to Lineup record

    game = db.relationship("Game", backref=db.backref("lineup_segments", lazy=True))




class Lineup(db.Model):
    """Multi-game lineup tracking with cached stats"""
    
    __tablename__ = "lineups"
    id = db.Column(db.Integer, primary_key=True)
    lineup_hash = db.Column(db.String(64), unique=True, nullable=False)
    players = db.Column(db.JSON, nullable=False)  # Sorted list of 5 player names
    display_name = db.Column(db.String(100), nullable=True)  # Optional custom name
    is_starting = db.Column(db.Boolean, default=False)  # Was this ever a starting lineup?
    
    # Cached aggregated stats
    total_seconds = db.Column(db.Integer, default=0)
    total_possessions = db.Column(db.Integer, default=0)
    points_scored = db.Column(db.Integer, default=0)
    points_allowed = db.Column(db.Integer, default=0)
    games_played = db.Column(db.Integer, default=0)
    segment_count = db.Column(db.Integer, default=0)
    
    # Calculated ratings
    ortg = db.Column(db.Float, default=0)
    drtg = db.Column(db.Float, default=0)
    net_rating = db.Column(db.Float, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    segments = db.relationship("LineupSegment", backref="lineup_ref", lazy=True)


class Possession(db.Model):
    """Distinct possession tracking for pace-adjusted stats"""

    __tablename__ = "possessions"
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    start_event_id = db.Column(
        db.Integer, db.ForeignKey("game_events.id"), nullable=False
    )
    end_event_id = db.Column(db.Integer, db.ForeignKey("game_events.id"), nullable=True)
    team_possession = db.Column(
        db.Boolean, default=True
    )  # True = our team, False = opponent
    quarter = db.Column(db.Integer, nullable=True)
    points = db.Column(db.Integer, default=0)  # Points scored on this possession
    play_id = db.Column(
        db.Integer, db.ForeignKey("plays.id"), nullable=True
    )  # Primary play used

    game = db.relationship("Game", backref=db.backref("possessions", lazy=True))
    start_event = db.relationship("GameEvent", foreign_keys=[start_event_id])
    end_event = db.relationship("GameEvent", foreign_keys=[end_event_id])
    play = db.relationship("Play", backref=db.backref("possessions", lazy=True))


class ShotZone(db.Model):
    """Expected point values for different court zones"""

    __tablename__ = "shot_zones"
    id = db.Column(db.Integer, primary_key=True)
    zone_name = db.Column(
        db.String(50), unique=True, nullable=False
    )  # e.g., "Corner_3", "Paint", "Midrange"
    zone_type = db.Column(
        db.String(20), nullable=False
    )  # "Corner_3", "Above_Break_3", "Paint", "Midrange", "FT"
    expected_value = db.Column(db.Float, nullable=False)  # Expected points per shot
    description = db.Column(db.String(255), nullable=True)
    x_min = db.Column(db.Float, nullable=True)  # Bounding box for zone classification
    x_max = db.Column(db.Float, nullable=True)
    y_min = db.Column(db.Float, nullable=True)
    y_max = db.Column(db.Float, nullable=True)


class PlayerLineupStats(db.Model):
    """Aggregated stats for a player during a specific lineup segment"""

    __tablename__ = "player_lineup_stats"
    id = db.Column(db.Integer, primary_key=True)
    lineup_segment_id = db.Column(
        db.Integer, db.ForeignKey("lineup_segments.id"), nullable=False
    )
    player_name = db.Column(db.String(100), nullable=False)

    # Counting stats during this segment
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
    reb_conceded = db.Column(db.Integer, default=0)  # Offensive rebounds conceded to opponents

    lineup_segment = db.relationship(
        "LineupSegment", backref=db.backref("player_stats", lazy=True)
    )
