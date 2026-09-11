# 🎯 Plays-Based Statistics Implementation Plan

**Status:** Planning Phase  
**Estimated Effort:** 4-6 hours  
**Priority:** Medium (detailed offensive analytics)  
**Created:** January 13, 2026

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Database Schema](#database-schema)
3. [Phase 1: Database Layer](#phase-1-database-layer)
4. [Phase 2: Data Access Layer](#phase-2-data-access-layer)
5. [Phase 3: PDF Export Layer](#phase-3-pdf-export-layer)
6. [Phase 4: UI Integration](#phase-4-ui-integration)
7. [Testing Strategy](#testing-strategy)
8. [Deployment Checklist](#deployment-checklist)

---

## Overview

### Current State
The basketball stats app tracks **aggregate player statistics** (points, rebounds, assists, FG%, etc.) but **does not track individual shots organized by plays**.

```
Current Flow:
Game Entry → PlayerStat (aggregate) → Box Score PDFs
                                    → Player Performance PDFs
                                    → Team Stats PDFs
```

### Target State
Add **plays-based shot tracking** for granular offensive analytics:

```
Target Flow:
Game Entry → PlayerStat (aggregate) + ShotEvent (detailed) → Box Score PDFs (existing)
                                    ↓                      ↓
                              Play Tagging               Plays-Based PDFs
                                    ↓                      ↓
                          Play Efficiency Analysis    Player Rankings per Play
                                    ↓                      ↓
                          Play Selection Insights     Coaching Analytics
```

### Benefits
- **Offensive Analysis:** See which plays work best
- **Player Insights:** Identify who's effective from which plays
- **Coaching Data:** Data-driven play selection
- **Performance Trends:** Track play efficiency over time
- **Player Rankings:** Show top scorers per play type

---

## Database Schema

### 1. New `Play` Table
Catalog of offensive plays/sets

```sql
CREATE TABLE plays (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    category VARCHAR(50),  -- e.g., "Pick & Roll", "Isolation", "Spot Up", "Transition", "Offensive Set"
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Example Data:**
| ID | Name | Category | Description |
|----|------|----------|-------------|
| 1 | Pick & Roll | Offensive Set | Screen at top of key |
| 2 | Isolation | Offensive Set | One-on-one post up |
| 3 | Spot Up | Offensive Set | Catch and shoot three |
| 4 | Fast Break | Transition | 3v2 or 2v1 outlet |
| 5 | Off-Ball Screen | Offensive Set | Screen away from ball |
| 6 | High Post | Offensive Set | Mid-range from elbow |
| 7 | Drive & Kick | Offensive Set | Drive dish to shooter |
| 8 | Transition Three | Transition | Early offensive three |

### 2. New `ShotEvent` Table
Individual shot attempts with play context

```sql
CREATE TABLE shot_events (
    id INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL FOREIGN KEY REFERENCES games(id),
    player_name VARCHAR(100) NOT NULL,
    play_id INTEGER FOREIGN KEY REFERENCES plays(id),
    shot_type VARCHAR(20),  -- "2PT", "3PT", "FT"
    result VARCHAR(10),     -- "Made", "Missed"
    points INTEGER,         -- 0, 1, 2, or 3
    shot_distance DECIMAL(5,2),  -- feet from basket
    shot_location VARCHAR(50),    -- "Left Wing", "Right Corner", "Center", etc.
    shooter_position VARCHAR(30), -- "PG", "SG", "SF", "PF", "C"
    assist_player VARCHAR(100),   -- who assisted (if made)
    defender VARCHAR(100),         -- primary defender
    quarter INTEGER,
    time_in_quarter VARCHAR(8),    -- "10:30" format
    game_score_margin INTEGER,     -- our score - their score at time of shot
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_shot_events_game ON shot_events(game_id);
CREATE INDEX idx_shot_events_play ON shot_events(play_id);
CREATE INDEX idx_shot_events_player ON shot_events(player_name);
CREATE INDEX idx_shot_events_result ON shot_events(result);
```

### 3. Updated `PlayerStat` Table (No Changes)
Keeps existing aggregate stats. ShotEvent provides granular data.

### 4. Relationships
```
Game (1) ──→ (Many) ShotEvent ──→ (1) Play
       ├─→ (Many) PlayerStat

Player (implicit) ──→ (Many) ShotEvent
Player (implicit) ──→ (Many) PlayerStat
```

---

## Phase 1: Database Layer

### 1.1 Create Migration

**File:** `migrations/versions/add_plays_and_shot_events.py`

```python
"""Add plays and shot events tables for granular offensive analytics.

Revision ID: add_plays_shot_events
Previous: [last migration]
Date: 2026-01-13
"""

from alembic import op
import sqlalchemy as sa


def upgrade():
    # Create Play table
    op.create_table(
        'plays',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create ShotEvent table
    op.create_table(
        'shot_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=False),
        sa.Column('player_name', sa.String(100), nullable=False),
        sa.Column('play_id', sa.Integer(), nullable=True),
        sa.Column('shot_type', sa.String(20), nullable=True),
        sa.Column('result', sa.String(10), nullable=False),
        sa.Column('points', sa.Integer(), nullable=False),
        sa.Column('shot_distance', sa.Float(), nullable=True),
        sa.Column('shot_location', sa.String(50), nullable=True),
        sa.Column('shooter_position', sa.String(30), nullable=True),
        sa.Column('assist_player', sa.String(100), nullable=True),
        sa.Column('defender', sa.String(100), nullable=True),
        sa.Column('quarter', sa.Integer(), nullable=True),
        sa.Column('time_in_quarter', sa.String(8), nullable=True),
        sa.Column('game_score_margin', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['game_id'], ['games.id']),
        sa.ForeignKeyConstraint(['play_id'], ['plays.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('idx_shot_events_game', 'shot_events', ['game_id'])
    op.create_index('idx_shot_events_play', 'shot_events', ['play_id'])
    op.create_index('idx_shot_events_player', 'shot_events', ['player_name'])
    op.create_index('idx_shot_events_result', 'shot_events', ['result'])


def downgrade():
    op.drop_index('idx_shot_events_result')
    op.drop_index('idx_shot_events_player')
    op.drop_index('idx_shot_events_play')
    op.drop_index('idx_shot_events_game')
    op.drop_table('shot_events')
    op.drop_table('plays')
```

### 1.2 Update Models

**File:** `core/models.py` (additions)

```python
class Play(db.Model):
    __tablename__ = 'plays'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))  # e.g., "Pick & Roll", "Isolation", etc.
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    shot_events = db.relationship('ShotEvent', backref=db.backref('play', lazy=True))
    
    def __repr__(self):
        return f'<Play {self.name}>'


class ShotEvent(db.Model):
    __tablename__ = 'shot_events'
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    player_name = db.Column(db.String(100), nullable=False)
    play_id = db.Column(db.Integer, db.ForeignKey('plays.id'))
    shot_type = db.Column(db.String(20))  # "2PT", "3PT", "FT"
    result = db.Column(db.String(10), nullable=False)  # "Made", "Missed"
    points = db.Column(db.Integer, nullable=False)  # 0, 1, 2, or 3
    shot_distance = db.Column(db.Float)  # feet
    shot_location = db.Column(db.String(50))  # "Left Wing", etc.
    shooter_position = db.Column(db.String(30))  # "PG", "SG", etc.
    assist_player = db.Column(db.String(100))
    defender = db.Column(db.String(100))
    quarter = db.Column(db.Integer)
    time_in_quarter = db.Column(db.String(8))  # "10:30"
    game_score_margin = db.Column(db.Integer)  # our score - their score
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    game = db.relationship('Game', backref=db.backref('shot_events', lazy=True))
    
    def __repr__(self):
        return f'<ShotEvent Game:{self.game_id} Player:{self.player_name} Play:{self.play_id}>'
```

### 1.3 Seed Initial Play Types

**File:** `scripts/seed_plays.py`

```python
#!/usr/bin/env python
"""Seed database with standard offensive plays."""

from core.models import db, Play
from app import create_app

app = create_app()

PLAYS = [
    {'name': 'Pick & Roll', 'category': 'Offensive Set', 'description': 'Screen at top of key'},
    {'name': 'Isolation', 'category': 'Offensive Set', 'description': 'One-on-one post up'},
    {'name': 'Spot Up', 'category': 'Offensive Set', 'description': 'Catch and shoot three'},
    {'name': 'Fast Break', 'category': 'Transition', 'description': '3v2 or 2v1 outlet'},
    {'name': 'Off-Ball Screen', 'category': 'Offensive Set', 'description': 'Screen away from ball'},
    {'name': 'High Post', 'category': 'Offensive Set', 'description': 'Mid-range from elbow'},
    {'name': 'Drive & Kick', 'category': 'Offensive Set', 'description': 'Drive dish to shooter'},
    {'name': 'Transition Three', 'category': 'Transition', 'description': 'Early offensive three'},
    {'name': 'Post Up', 'category': 'Offensive Set', 'description': 'Low post scoring'},
    {'name': 'Handoff', 'category': 'Offensive Set', 'description': 'Guard to guard/wing handoff'},
]

with app.app_context():
    for play_data in PLAYS:
        existing = Play.query.filter_by(name=play_data['name']).first()
        if not existing:
            play = Play(**play_data)
            db.session.add(play)
            print(f"✅ Added play: {play_data['name']}")
        else:
            print(f"⏭️  Play already exists: {play_data['name']}")
    
    db.session.commit()
    print("\n🎯 Seeding complete!")
```

---

## Phase 2: Data Access Layer

### 2.1 Create PlaysStatsAggregator

**File:** `core/plays_stats.py`

```python
"""Aggregate plays-based statistics for reporting and analysis."""

from sqlalchemy import func, desc
from core.models import db, ShotEvent, Play, PlayerStat, Game


class PlaysStatsAggregator:
    """Calculate plays-based statistics."""
    
    @staticmethod
    def get_game_plays_stats(game_id):
        """
        Get all plays used in a game with shot statistics.
        
        Returns:
            {
                'game': Game object,
                'plays_used': [{'play_id', 'play_name', 'attempts', 'made', 'fg%', 'ppa'}, ...],
                'plays_coverage': X%,  # percentage of shots from tracked plays
                'shots_by_play': {...}
            }
        """
        game = Game.query.get_or_404(game_id)
        
        # Get all shots in game
        all_shots = ShotEvent.query.filter_by(game_id=game_id).all()
        total_shots = len(all_shots)
        tracked_shots = len([s for s in all_shots if s.play_id is not None])
        plays_coverage = (tracked_shots / total_shots * 100) if total_shots > 0 else 0
        
        # Aggregate by play
        plays_stats = db.session.query(
            Play.id,
            Play.name,
            func.count(ShotEvent.id).label('attempts'),
            func.sum(func.cast(ShotEvent.result == 'Made', db.Integer)).label('made'),
        ).join(
            ShotEvent, Play.id == ShotEvent.play_id
        ).filter(
            ShotEvent.game_id == game_id
        ).group_by(
            Play.id, Play.name
        ).all()
        
        # Calculate metrics
        plays_used = []
        for play_id, play_name, attempts, made in plays_stats:
            fg_pct = (made / attempts * 100) if attempts > 0 else 0
            ppa = (made / attempts) if attempts > 0 else 0  # Points per attempt
            
            plays_used.append({
                'play_id': play_id,
                'play_name': play_name,
                'attempts': attempts,
                'made': made,
                'fg_pct': round(fg_pct, 1),
                'ppa': round(ppa, 2)
            })
        
        return {
            'game': game,
            'plays_used': sorted(plays_used, key=lambda x: x['attempts'], reverse=True),
            'plays_coverage': round(plays_coverage, 1),
            'total_shots': total_shots,
            'tracked_shots': tracked_shots
        }
    
    @staticmethod
    def get_player_plays_stats(player_name, game_id=None):
        """
        Get player's performance by play type.
        
        Args:
            player_name: Player name
            game_id: Optional - filter to single game
        
        Returns:
            {
                'player_name': str,
                'plays_breakdown': [{'play_name', 'attempts', 'made', 'fg%', 'ppa'}, ...],
                'total_attempts': int,
                'total_made': int,
                'overall_ppa': float
            }
        """
        query = ShotEvent.query.filter_by(player_name=player_name)
        if game_id:
            query = query.filter_by(game_id=game_id)
        
        all_shots = query.all()
        total_attempts = len(all_shots)
        total_made = len([s for s in all_shots if s.result == 'Made'])
        
        # Aggregate by play
        plays_breakdown = db.session.query(
            Play.name,
            func.count(ShotEvent.id).label('attempts'),
            func.sum(func.cast(ShotEvent.result == 'Made', db.Integer)).label('made'),
        ).join(
            ShotEvent, Play.id == ShotEvent.play_id
        ).filter(
            ShotEvent.player_name == player_name
        )
        
        if game_id:
            plays_breakdown = plays_breakdown.filter(ShotEvent.game_id == game_id)
        
        plays_breakdown = plays_breakdown.group_by(Play.name).all()
        
        breakdown = []
        for play_name, attempts, made in plays_breakdown:
            fg_pct = (made / attempts * 100) if attempts > 0 else 0
            ppa = (made / attempts) if attempts > 0 else 0
            
            breakdown.append({
                'play_name': play_name,
                'attempts': attempts,
                'made': made,
                'fg_pct': round(fg_pct, 1),
                'ppa': round(ppa, 2)
            })
        
        return {
            'player_name': player_name,
            'plays_breakdown': sorted(breakdown, key=lambda x: x['attempts'], reverse=True),
            'total_attempts': total_attempts,
            'total_made': total_made,
            'overall_ppa': round(total_made / total_attempts, 2) if total_attempts > 0 else 0
        }
    
    @staticmethod
    def get_team_plays_rankings(game_id):
        """
        Get player rankings for each play type in a game.
        
        Returns:
            {
                'game': Game,
                'plays': [
                    {
                        'play_name': str,
                        'attempts': int,
                        'fg%': float,
                        'player_rankings': [
                            {'rank': 1, 'player': 'John', 'points': 5, 'attempts': 2},
                            ...
                        ]
                    },
                    ...
                ]
            }
        """
        game = Game.query.get_or_404(game_id)
        
        # Get all plays used in game
        plays_in_game = db.session.query(Play.id, Play.name).join(
            ShotEvent, Play.id == ShotEvent.play_id
        ).filter(
            ShotEvent.game_id == game_id
        ).distinct().all()
        
        plays_data = []
        
        for play_id, play_name in plays_in_game:
            # Get stats for this play
            play_shots = db.session.query(
                ShotEvent.player_name,
                func.count(ShotEvent.id).label('attempts'),
                func.sum(ShotEvent.points).label('points')
            ).filter(
                ShotEvent.game_id == game_id,
                ShotEvent.play_id == play_id
            ).group_by(
                ShotEvent.player_name
            ).order_by(
                desc('points')
            ).all()
            
            total_attempts = sum(s[1] for s in play_shots)
            total_made = sum(1 for s in ShotEvent.query.filter(
                ShotEvent.game_id == game_id,
                ShotEvent.play_id == play_id,
                ShotEvent.result == 'Made'
            ).all())
            fg_pct = (total_made / total_attempts * 100) if total_attempts > 0 else 0
            
            player_rankings = []
            for rank, (player_name, attempts, points) in enumerate(play_shots, 1):
                player_rankings.append({
                    'rank': rank,
                    'player': player_name,
                    'points': points or 0,
                    'attempts': attempts
                })
            
            plays_data.append({
                'play_id': play_id,
                'play_name': play_name,
                'attempts': total_attempts,
                'fg_pct': round(fg_pct, 1),
                'player_rankings': player_rankings
            })
        
        return {
            'game': game,
            'plays': sorted(plays_data, key=lambda x: x['attempts'], reverse=True)
        }
```

---

## Phase 3: PDF Export Layer

### 3.1 Create Plays-Based PDF Routes

**File:** `web/routes/pdf_export.py`

```python
"""PDF export routes for plays-based statistics."""

from flask import Blueprint, request, send_file, jsonify
from flask_login import login_required
from io import BytesIO
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.units import inch
from datetime import datetime

from core.models import Game, db
from core.plays_stats import PlaysStatsAggregator

pdf_export_bp = Blueprint('pdf_export', __name__)


def register_pdf_routes(app):
    """Register PDF export routes with Flask app."""
    app.register_blueprint(pdf_export_bp)


@pdf_export_bp.route('/api/pdf/game/<int:game_id>')
@login_required
def export_game_pdf(game_id):
    """Export game plays report as PDF."""
    game = Game.query.get_or_404(game_id)
    stats = PlaysStatsAggregator.get_game_plays_stats(game_id)
    
    # Create PDF
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1f77b4'),
        spaceAfter=12,
        alignment=1  # center
    )
    story.append(Paragraph(f"Game Report - {game.date} vs {game.opponent}", title_style))
    story.append(Spacer(1, 0.3*inch))
    
    # Game summary
    summary_data = [
        ['Date', game.date],
        ['Opponent', game.opponent],
        ['Score', f"{game.team_score} - {game.opponent_score}"],
        ['Result', 'W' if game.result == 'W' else 'L'],
    ]
    summary_table = Table(summary_data, colWidths=[1.5*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Plays used
    story.append(Paragraph(f"<b>Plays Used ({len(stats['plays_used'])} types)</b>", styles['Heading2']))
    story.append(Spacer(1, 0.15*inch))
    
    plays_data = [['Play', 'Attempts', 'Made', 'FG%', 'PPA']]
    for play in stats['plays_used']:
        plays_data.append([
            play['play_name'],
            str(play['attempts']),
            str(play['made']),
            f"{play['fg_pct']}%",
            str(play['ppa'])
        ])
    
    plays_table = Table(plays_data, colWidths=[2*inch, 1*inch, 1*inch, 1*inch, 1*inch])
    plays_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(plays_table)
    story.append(Spacer(1, 0.2*inch))
    
    # Coverage note
    coverage_text = f"<i>Play Coverage: {stats['plays_coverage']}% ({stats['tracked_shots']}/{stats['total_shots']} shots tracked)</i>"
    story.append(Paragraph(coverage_text, styles['Normal']))
    
    # Build PDF
    doc.build(story)
    pdf_buffer.seek(0)
    
    filename = f"game_plays_{game.date}_{game.opponent.replace(' ', '_')}.pdf"
    return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)


@pdf_export_bp.route('/api/pdf/team/<int:game_id>')
@login_required
def export_team_plays_pdf(game_id):
    """Export team plays report with player rankings as PDF."""
    game = Game.query.get_or_404(game_id)
    stats = PlaysStatsAggregator.get_team_plays_rankings(game_id)
    
    # Create PDF (landscape for more columns)
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=landscape(letter))
    story = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor('#1f77b4'),
        spaceAfter=12,
        alignment=1
    )
    story.append(Paragraph(f"Team Plays Analysis - {game.date} vs {game.opponent}", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # For each play, create a table with player rankings
    for idx, play in enumerate(stats['plays']):
        if idx > 0:
            story.append(PageBreak())
        
        # Play header
        play_header = f"<b>{play['play_name']}</b> ({play['attempts']} attempts, {play['fg_pct']}% FG)"
        story.append(Paragraph(play_header, styles['Heading3']))
        story.append(Spacer(1, 0.15*inch))
        
        # Player rankings table
        ranking_data = [['Rank', 'Player', 'Points', 'Attempts']]
        for ranking in play['player_rankings']:
            ranking_data.append([
                str(ranking['rank']),
                ranking['player'],
                str(ranking['points']),
                str(ranking['attempts'])
            ])
        
        ranking_table = Table(ranking_data, colWidths=[0.75*inch, 2*inch, 1.25*inch, 1.25*inch])
        ranking_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2ca02c')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')])
        ]))
        story.append(ranking_table)
        story.append(Spacer(1, 0.3*inch))
    
    # Build PDF
    doc.build(story)
    pdf_buffer.seek(0)
    
    filename = f"team_plays_{game.date}_{game.opponent.replace(' ', '_')}.pdf"
    return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)


@pdf_export_bp.route('/api/pdf/player/<player_name>')
@login_required
def export_player_plays_pdf(player_name):
    """Export player plays breakdown as PDF."""
    game_id = request.args.get('game_id', type=int)
    
    stats = PlaysStatsAggregator.get_player_plays_stats(player_name, game_id)
    
    # Create PDF
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor('#1f77b4'),
        spaceAfter=12,
        alignment=1
    )
    period = f"Game-Specific" if game_id else "Season"
    story.append(Paragraph(f"{player_name} - Plays Breakdown ({period})", title_style))
    story.append(Spacer(1, 0.3*inch))
    
    # Summary stats
    summary_data = [
        ['Total Attempts', stats['total_attempts']],
        ['Total Made', stats['total_made']],
        ['Overall PPA', f"{stats['overall_ppa']:.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[1.5*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Plays breakdown
    story.append(Paragraph("<b>Performance by Play Type</b>", styles['Heading2']))
    story.append(Spacer(1, 0.15*inch))
    
    plays_data = [['Play', 'Attempts', 'Made', 'FG%', 'PPA']]
    for play in stats['plays_breakdown']:
        plays_data.append([
            play['play_name'],
            str(play['attempts']),
            str(play['made']),
            f"{play['fg_pct']}%",
            f"{play['ppa']:.2f}"
        ])
    
    plays_table = Table(plays_data, colWidths=[2*inch, 1*inch, 1*inch, 1*inch, 1*inch])
    plays_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#764ba2')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')])
    ]))
    story.append(plays_table)
    
    # Build PDF
    doc.build(story)
    pdf_buffer.seek(0)
    
    filename = f"{player_name.replace(' ', '_')}_plays_{period}.pdf"
    return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)


@pdf_export_bp.route('/api/pdf/game/<int:game_id>/preview')
@login_required
def preview_game_plays(game_id):
    """Get JSON preview of game plays report."""
    stats = PlaysStatsAggregator.get_game_plays_stats(game_id)
    
    return jsonify({
        'plays_used': len(stats['plays_used']),
        'plays_coverage': stats['plays_coverage'],
        'total_shots': stats['total_shots'],
        'tracked_shots': stats['tracked_shots'],
        'plays': stats['plays_used']
    })


@pdf_export_bp.route('/api/pdf/team/<int:game_id>/preview')
@login_required
def preview_team_plays(game_id):
    """Get JSON preview of team plays report."""
    stats = PlaysStatsAggregator.get_team_plays_rankings(game_id)
    
    return jsonify({
        'game': {
            'date': stats['game'].date,
            'opponent': stats['game'].opponent,
            'score': f"{stats['game'].team_score}-{stats['game'].opponent_score}"
        },
        'plays': [
            {
                'name': p['play_name'],
                'attempts': p['attempts'],
                'fg_pct': p['fg_pct'],
                'player_rankings': p['player_rankings']
            }
            for p in stats['plays']
        ]
    })
```

---

## Phase 4: UI Integration

### 4.1 Add Shot Entry Form

Update game detail page to include shot entry with play tagging.

### 4.2 Update Templates

Add export buttons to game and player templates.

---

## Testing Strategy

### Unit Tests
- Test PlaysStatsAggregator queries
- Test PDF generation with sample data
- Test edge cases (no shots, no plays, NULL play_id)

### Integration Tests
- Test full flow: enter shot → tag play → generate PDF
- Test all three PDF export endpoints
- Test preview JSON endpoints

### Manual Testing
1. Create test game with sample shots
2. Tag shots with plays
3. Export each PDF type
4. Verify correctness in PDF viewer
5. Test error cases

---

## Deployment Checklist

### Pre-Deployment
- [ ] All unit and integration tests passing
- [ ] Database migration tested locally
- [ ] Initial plays seeded correctly
- [ ] PDF generation tested with sample data
- [ ] UI templates updated and tested
- [ ] Documentation updated
- [ ] Code reviewed

### Deployment Steps
1. Create feature branch from main
2. Implement Phase 1 (DB schema)
3. Implement Phase 2 (data access)
4. Implement Phase 3 (PDF export)
5. Implement Phase 4 (UI)
6. Test full flow
7. Create PR with comprehensive description
8. Merge to main after approval
9. Deploy to production
10. Monitor for errors

### Post-Deployment
- [ ] Monitor PDF generation performance
- [ ] Verify data accuracy in PDFs
- [ ] Collect user feedback
- [ ] Plan enhancements based on usage

---

## Implementation Timeline

| Phase | Estimated Time | Status |
|-------|----------------|--------|
| Phase 1: Database | 30-45 min | TODO |
| Phase 2: Data Access | 1-1.5 hours | TODO |
| Phase 3: PDF Export | 1.5-2 hours | TODO |
| Phase 4: UI Integration | 45-60 min | TODO |
| Testing | 1-2 hours | TODO |
| **Total** | **4-6 hours** | TODO |

---

## Next Steps

1. **Review this plan** - ensure approach is sound
2. **Create migration** - implement Phase 1
3. **Add models** - update core/models.py
4. **Seed plays** - run initial data script
5. **Build aggregator** - implement PlaysStatsAggregator
6. **Create PDF routes** - implement PDF export
7. **Add UI** - integrate into templates
8. **Test thoroughly** - manual and automated
9. **Deploy** - merge to main and deploy

---

**Questions or concerns?** Review this plan section by section and let's discuss before implementation.
