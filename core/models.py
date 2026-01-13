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
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)


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
    source = db.Column(db.String(20), default="IMPORT") # LIVE, IMPORT, MANUAL

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
    plus_minus = db.Column(db.Integer, default=0) # +/- Stat
    
    # Relationship to Game
    game = db.relationship("Game", backref=db.backref("stats", lazy=True))


class ShotEvent(db.Model):
    __tablename__ = "shot_events"
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    player_name = db.Column(db.String(100))
    shot_type = db.Column(db.String(10)) # 2pt, 3pt, ft
    result = db.Column(db.String(10)) # made, missed
    points = db.Column(db.Integer, default=0)
    x_loc = db.Column(db.Float, nullable=True) # Normalized 0-500
    y_loc = db.Column(db.Float, nullable=True) # Normalized 0-470
    quarter = db.Column(db.Integer)
    play_id = db.Column(db.Integer, db.ForeignKey("plays.id"), nullable=True) # Tagged play
    
    game = db.relationship("Game", backref=db.backref("shots", lazy=True))
    play = db.relationship("Play", backref=db.backref("shot_events", lazy=True))


class GameEvent(db.Model):
    __tablename__ = "game_events"
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    event_type = db.Column(db.String(50)) # SHOT_2PT, SHOT_3PT, TURNOVER, SUB_IN, SUB_OUT, OPP_SCORE
    player_name = db.Column(db.String(100), nullable=True)
    detail = db.Column(db.String(255), nullable=True) # e.g. amount of points for opp score
    timestamp = db.Column(db.Integer, default=0) # generic ordering index
    shot_attempt = db.Column(db.String(10), nullable=True) # 'attempted' or 'made' for shots
    play_id = db.Column(db.Integer, db.ForeignKey("plays.id"), nullable=True) # Tagged play
    
    game = db.relationship("Game", backref=db.backref("events", lazy=True))
    play = db.relationship("Play", backref=db.backref("game_events", lazy=True))


class Play(db.Model):
    __tablename__ = "plays"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    play_type = db.Column(db.String(50), default="Offense")  # Offense, Defense, Special
    image_filename = db.Column(db.String(255), nullable=True) # Stored in uploads/plays/
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
