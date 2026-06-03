"""PDF Export Module with Plays-Based Statistics

Generates professional PDF reports for:
- Individual games with plays analysis
- Player performance reports with plays breakdown
- Team statistics with plays-based metrics

Requirements:
- reportlab: PDF generation
- python-dateutil: Date handling
"""

# Import styles and base classes only - keep heavy imports inside methods
from io import BytesIO
from datetime import datetime
from flask import current_app
from core.models import Game, Player, ShotEvent, GameEvent, Play, PlayerStat
from sqlalchemy import func, and_

class PlaysBasedPDFGenerator:
    """Generate professional PDF reports with plays-based statistics."""

    def __init__(self):
        """Initialize PDF generator with style definitions."""
        # Lazy import of reportlab components
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.lib import colors

        self.colors = colors
        self.styles = getSampleStyleSheet()
        self.ParagraphStyle = ParagraphStyle
        self.TA_CENTER = TA_CENTER
        self.TA_LEFT = TA_LEFT
        self.TA_RIGHT = TA_RIGHT
        self.inch = inch
        
        self.setup_custom_styles()
        self.pagesize = letter
        self.left_margin = 0.5 * inch
        self.right_margin = 0.5 * inch
        self.top_margin = 0.75 * inch
        self.bottom_margin = 0.75 * inch

    def setup_custom_styles(self):
        """Define custom paragraph styles for reports."""
        # Title style
        self.styles.add(self.ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=self.colors.HexColor('#1f2937'),
            spaceAfter=12,
            alignment=self.TA_CENTER,
            fontName='Helvetica-Bold'
        ))

        # Subtitle style
        self.styles.add(self.ParagraphStyle(
            name='CustomSubtitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=self.colors.HexColor('#4b5563'),
            spaceAfter=10,
            alignment=self.TA_CENTER
        ))

        # Section heading
        self.styles.add(self.ParagraphStyle(
            name='SectionHeading',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=self.colors.HexColor('#1f2937'),
            spaceAfter=8,
            spaceBefore=10,
            fontName='Helvetica-Bold',
            borderColor=self.colors.HexColor('#208dd1'),
            borderWidth=2,
            borderPadding=5
        ))

        # Normal body text
        self.styles.add(self.ParagraphStyle(
            name='CustomBodyText',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=8
        ))

        # Player name style
        self.styles.add(self.ParagraphStyle(
            name='PlayerName',
            parent=self.styles['Heading3'],
            fontSize=11,
            textColor=self.colors.HexColor('#1f2937'),
            spaceAfter=4,
            fontName='Helvetica-Bold'
        ))

    def generate_game_report_pdf(self, game_id):
        """Generate comprehensive game report with plays analysis.

        Args:
            game_id (int): Game database ID

        Returns:
            BytesIO: PDF document in memory
        """
        # Lazy import reportlab components
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
        
        game = Game.query.get(game_id)
        if not game:
            raise ValueError(f"Game {game_id} not found")

        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=self.pagesize,
            leftMargin=self.left_margin,
            rightMargin=self.right_margin,
            topMargin=self.top_margin,
            bottomMargin=self.bottom_margin
        )

        story = []

        # Header
        story.append(Paragraph(
            f"Game Report: {game.opponent}",
            self.styles['CustomTitle']
        ))

        game_date = game.date.strftime('%B %d, %Y') if hasattr(game.date, 'strftime') else str(game.date)
        story.append(Paragraph(
            f"{game_date} | {game.team_score} - {game.opponent_score}",
            self.styles['CustomSubtitle']
        ))
        story.append(Spacer(1, 0.2 * self.inch))

        # Basic Stats Section
        story.append(Paragraph("Game Summary", self.styles['SectionHeading']))
        basic_stats_data = [
            ['Metric', 'Value'],
            ['Date', game_date],
            ['Opponent', game.opponent],
            ['Game Type', game.game_type or 'Regular'],
            ['Our Score', str(game.team_score)],
            ['Opponent Score', str(game.opponent_score)],
            ['Result', 'W' if game.team_score > game.opponent_score else 'L'],
        ]
        basic_stats_table = Table(basic_stats_data, colWidths=[2 * self.inch, 2 * self.inch])
        basic_stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors.HexColor('#208dd1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), self.colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, self.colors.black)
        ]))
        story.append(basic_stats_table)
        story.append(Spacer(1, 0.2 * self.inch))

        # Plays-Based Analysis
        story.extend(self._generate_plays_analysis(game))
        story.append(Spacer(1, 0.2 * self.inch))

        # Shot Events Analysis
        story.extend(self._generate_shot_events_analysis(game))
        story.append(Spacer(1, 0.2 * self.inch))

        # Player Analysis Section - NEW
        story.extend(self._generate_player_analysis_section(game))
        story.append(Spacer(1, 0.2 * self.inch))

        # Game Events Timeline
        story.extend(self._generate_game_events_section(game))

        # Build PDF
        doc.build(story)
        pdf_buffer.seek(0)
        
        # Explicitly clean up
        del doc
        del story
        
        return pdf_buffer

    def generate_player_report_pdf(self, player_id):
        """Generate comprehensive player report with plays breakdown.

        Args:
            player_id (int): Player database ID

        Returns:
            BytesIO: PDF document in memory
        """
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        
        player = Player.query.get(player_id)
        if not player:
            raise ValueError(f"Player {player_id} not found")

        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=self.pagesize,
            leftMargin=self.left_margin,
            rightMargin=self.right_margin,
            topMargin=self.top_margin,
            bottomMargin=self.bottom_margin
        )

        story = []

        # Header
        story.append(Paragraph(
            f"Player Report: {player.name}",
            self.styles['CustomTitle']
        ))
        story.append(Paragraph(
            f"Generated on {datetime.now().strftime('%B %d, %Y')}",
            self.styles['CustomSubtitle']
        ))
        story.append(Spacer(1, 0.2 * self.inch))

        # Career Stats
        story.append(Paragraph("Career Statistics", self.styles['SectionHeading']))
        career_stats = self._calculate_player_career_stats(player)
        story.append(self._create_player_stats_table(career_stats))
        story.append(Spacer(1, 0.2 * self.inch))

        # Plays-Based Performance
        story.extend(self._generate_player_plays_analysis(player))
        story.append(Spacer(1, 0.2 * self.inch))

        # Shot Performance by Play
        story.extend(self._generate_player_shot_by_play_analysis(player))
        story.append(Spacer(1, 0.2 * self.inch))

        # Recent Games
        story.extend(self._generate_player_recent_games(player))

        # Build PDF
        doc.build(story)
        pdf_buffer.seek(0)
        
        # Explicit cleanup
        del doc
        del story
        
        return pdf_buffer

    def generate_team_report_pdf(self):
        """Generate comprehensive team report with plays-based analysis.

        Returns:
            BytesIO: PDF document in memory
        """
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=self.pagesize,
            leftMargin=self.left_margin,
            rightMargin=self.right_margin,
            topMargin=self.top_margin,
            bottomMargin=self.bottom_margin
        )

        story = []

        # Header
        story.append(Paragraph(
            "Team Statistical Report",
            self.styles['CustomTitle']
        ))
        story.append(Paragraph(
            f"Generated on {datetime.now().strftime('%B %d, %Y')}",
            self.styles['CustomSubtitle']
        ))
        story.append(Spacer(1, 0.2 * self.inch))

        # Season Overview
        story.append(Paragraph("Season Overview", self.styles['SectionHeading']))
        team_stats = self._calculate_team_stats()
        story.append(self._create_team_summary_table(team_stats))
        story.append(Spacer(1, 0.2 * self.inch))

        # Plays-Based Team Analysis
        story.extend(self._generate_team_plays_analysis())
        story.append(Spacer(1, 0.2 * self.inch))

        # Player Performance Summary
        story.extend(self._generate_team_player_summary())
        story.append(Spacer(1, 0.2 * self.inch))

        # Plays Effectiveness
        story.extend(self._generate_plays_effectiveness())

        # Build PDF
        doc.build(story)
        pdf_buffer.seek(0)
        
        # Explicit cleanup
        del doc
        del story
        
        return pdf_buffer

    # ============ Helper Methods for Games ============

    def _generate_plays_analysis(self, game):
        """Generate plays analysis section for a game."""
        from reportlab.platypus import Table, TableStyle, Paragraph
        
        story = []
        story.append(Paragraph("Plays Analysis", self.styles['SectionHeading']))

        # Get all plays used in this game
        plays_stats = self._calculate_game_plays_stats(game.id)

        if not plays_stats:
            story.append(Paragraph("No plays recorded for this game.", self.styles['CustomBodyText']))
            return story

        # Create plays statistics table
        plays_data = [['Play Name', 'Count', 'Shots', 'Made', 'FG%']]
        for play_stat in plays_stats:
            fg_pct = (play_stat['made'] / play_stat['shots']) * 100 if play_stat['shots'] > 0 else 0
            plays_data.append([
                play_stat['play_name'],
                str(play_stat['count']),
                str(play_stat['shots']),
                str(play_stat['made']),
                f"{fg_pct:.1f}%"
            ])

        plays_table = Table(plays_data, colWidths=[2 * self.inch, 0.8 * self.inch, 0.8 * self.inch, 0.8 * self.inch, 0.8 * self.inch])
        plays_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors.HexColor('#208dd1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), self.colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, self.colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 9)
        ]))
        story.append(plays_table)
        return story

    def _generate_shot_events_analysis(self, game):
        """Generate shot events analysis for a game."""
        from reportlab.platypus import Table, TableStyle, Paragraph
        
        story = []
        story.append(Paragraph("Shot Events Analysis", self.styles['SectionHeading']))

        shot_events = ShotEvent.query.filter_by(game_id=game.id).all()

        if not shot_events:
            story.append(Paragraph("No shot events recorded for this game.", self.styles['CustomBodyText']))
            return story

        total_shots = len(shot_events)
        made_shots = sum(1 for s in shot_events if s.result == 'made')
        fg_pct = (made_shots / total_shots * 100) if total_shots > 0 else 0

        # Shot summary
        shot_data = [
            ['Metric', 'Value'],
            ['Total Shots', str(total_shots)],
            ['Made', str(made_shots)],
            ['Missed', str(total_shots - made_shots)],
            ['FG %', f"{fg_pct:.1f}%"],
        ]

        shot_table = Table(shot_data, colWidths=[2 * self.inch, 2 * self.inch])
        shot_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors.HexColor('#208dd1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, self.colors.black)
        ]))
        story.append(shot_table)
        return story

    def _generate_player_analysis_section(self, game):
        """Generate comprehensive player analysis for all players in game."""
        from reportlab.platypus import Paragraph, Spacer, PageBreak
        
        story = []
        story.append(Paragraph("Player Analysis", self.styles['SectionHeading']))
        
        # Get all player stats for this game
        player_stats = PlayerStat.query.filter_by(game_id=game.id).order_by(
            PlayerStat.points.desc()
        ).all()
        
        if not player_stats:
            story.append(Paragraph("No player statistics recorded for this game.", self.styles['CustomBodyText']))
            return story
        
        # Create a card for each player
        for idx, p_stat in enumerate(player_stats):
            story.extend(self._create_player_stat_card(p_stat))
            
            # Add page break after every 3 players to avoid crowding
            if (idx + 1) % 3 == 0 and idx + 1 < len(player_stats):
                story.append(PageBreak())
            else:
                story.append(Spacer(1, 0.15 * self.inch))
        
        return story

    def _create_player_stat_card(self, player_stat):
        """Create a single player stat card for game report."""
        from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
        
        story = []
        
        # Player name header
        story.append(Paragraph(
            f"{player_stat.player_name}",
            self.styles['PlayerName']
        ))
        
        # Main stats line (scoring focus)
        main_stats_text = f"{player_stat.fgm} points | {player_stat.dreb} defensive rebounds | {player_stat.fga} attempts | {player_stat.oreb} offensive rebounds"
        story.append(Paragraph(main_stats_text, self.styles['CustomBodyText']))
        
        # Shooting stats table (FG, T3, T2, FT)
        shooting_data = [
            ['FG', 'T3', 'T2', 'FT'],
            [
                f"{player_stat.fgm}\n{player_stat.fga}\n{player_stat.fg_percent:.1f}%",
                f"{player_stat.tpm}\n{player_stat.tpa}\n{player_stat.tp_percent:.1f}%",
                f"{player_stat.fgm - player_stat.tpm}\n{player_stat.fga - player_stat.tpa}\n{((player_stat.fgm - player_stat.tpm) / (player_stat.fga - player_stat.tpa) * 100) if (player_stat.fga - player_stat.tpa) > 0 else 0:.1f}%",
                f"{player_stat.ftm}\n{player_stat.fta}\n{player_stat.ft_percent:.1f}%"
            ]
        ]
        
        shooting_table = Table(shooting_data, colWidths=[1.2 * self.inch, 1.2 * self.inch, 1.2 * self.inch, 1.2 * self.inch])
        shooting_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors.HexColor('#208dd1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BACKGROUND', (0, 1), (-1, -1), self.colors.HexColor('#f3f4f6')),
            ('GRID', (0, 0), (-1, -1), 1, self.colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        story.append(shooting_table)
        story.append(Spacer(1, 0.1 * self.inch))
        
        # Detailed stats grid
        minutes_display = player_stat.minutes if player_stat.minutes else "N/A"
        efficiency = (player_stat.points / player_stat.fga * 100) if player_stat.fga > 0 else 0
        
        # More readable layout - use two columns
        detailed_stats = [
            ['Minuti', minutes_display, 'R. difensivi', str(player_stat.dreb)],
            ['+/-', str(player_stat.plus_minus), 'R. offensivi', str(player_stat.oreb)],
            ['Efficienza', f"{efficiency:.1f}", 'Assist', str(player_stat.ast)],
            ['Stoppate', str(player_stat.blk), 'Perse', str(player_stat.tov)],
            ['Rubate', str(player_stat.stl), 'Falli', str(player_stat.pf)]
        ]
        
        details_table = Table(detailed_stats, colWidths=[1 * self.inch, 1 * self.inch, 1 * self.inch, 1 * self.inch])
        details_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (0, -1), self.colors.HexColor('#e5e7eb')),
            ('BACKGROUND', (2, 0), (2, -1), self.colors.HexColor('#e5e7eb')),
            ('GRID', (0, 0), (-1, -1), 0.5, self.colors.HexColor('#d1d5db')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        story.append(details_table)
        
        return story

    def _generate_game_events_section(self, game):
        """Generate game events section."""
        from reportlab.platypus import Table, TableStyle, Paragraph
        
        story = []
        story.append(Paragraph("Game Events", self.styles['SectionHeading']))

        game_events = GameEvent.query.filter_by(game_id=game.id).limit(20).all()

        if not game_events:
            story.append(Paragraph("No game events recorded.", self.styles['CustomBodyText']))
            return story

        events_data = [['Player', 'Event Type', 'Quarter', 'Play']]
        for event in game_events:
            play_name = event.play.name if event.play else 'None'
            events_data.append([
                event.player_name or 'N/A',
                event.event_type,
                str(event.quarter if hasattr(event, 'quarter') else 'N/A'),
                play_name
            ])

        events_table = Table(events_data, colWidths=[1.5 * self.inch, 1.5 * self.inch, 0.8 * self.inch, 2 * self.inch])
        events_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors.HexColor('#208dd1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BACKGROUND', (0, 1), (-1, -1), self.colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, self.colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8)
        ]))
        story.append(events_table)
        return story

    def _calculate_game_plays_stats(self, game_id):
        """Calculate plays statistics for a game."""
        plays_data = {}

        # Get shot events
        shots = ShotEvent.query.filter_by(game_id=game_id).all()
        for shot in shots:
            if shot.play_id:
                play_name = shot.play.name if shot.play else f"Play {shot.play_id}"
                if play_name not in plays_data:
                    plays_data[play_name] = {
                        'play_name': play_name,
                        'count': 0,
                        'shots': 0,
                        'made': 0
                    }
                plays_data[play_name]['count'] += 1
                plays_data[play_name]['shots'] += 1
                if shot.result == 'made':
                    plays_data[play_name]['made'] += 1

        # Get game events
        events = GameEvent.query.filter_by(game_id=game_id).all()
        for event in events:
            if event.play_id:
                play_name = event.play.name if event.play else f"Play {event.play_id}"
                if play_name not in plays_data:
                    plays_data[play_name] = {
                        'play_name': play_name,
                        'count': 0,
                        'shots': 0,
                        'made': 0
                    }
                plays_data[play_name]['count'] += 1

        return list(plays_data.values())

    # ============ Helper Methods for Players ============

    def _calculate_player_career_stats(self, player):
        """Calculate player career statistics."""
        total_points = 0
        total_games = 0
        total_shots = 0
        made_shots = 0

        # Query all shots by this player
        shots = ShotEvent.query.filter_by(player_name=player.name).all()
        total_shots = len(shots)
        made_shots = sum(1 for s in shots if s.result == 'made')
        total_points = sum(s.points for s in shots if s.result == 'made')

        # Get unique games
        games = Game.query.filter(
            Game.id.in_([s.game_id for s in shots])
        ).all()
        total_games = len(set(games))

        fg_pct = (made_shots / total_shots * 100) if total_shots > 0 else 0
        ppg = total_points / total_games if total_games > 0 else 0

        return {
            'total_games': total_games,
            'total_shots': total_shots,
            'made_shots': made_shots,
            'fg_pct': fg_pct,
            'total_points': total_points,
            'ppg': ppg
        }

    def _create_player_stats_table(self, stats):
        """Create player statistics table."""
        from reportlab.platypus import Table, TableStyle
        
        stats_data = [
            ['Metric', 'Value'],
            ['Games Played', str(stats['total_games'])],
            ['Total Shots', str(stats['total_shots'])],
            ['Made Shots', str(stats['made_shots'])],
            ['FG %', f"{stats['fg_pct']:.1f}%"],
            ['Total Points', str(stats['total_points'])],
            ['PPG', f"{stats['ppg']:.1f}"],
        ]

        table = Table(stats_data, colWidths=[2.5 * self.inch, 1.5 * self.inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors.HexColor('#208dd1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, self.colors.black)
        ]))
        return table

    def _generate_player_plays_analysis(self, player):
        """Generate plays performance analysis for player."""
        from reportlab.platypus import Table, TableStyle, Paragraph
        
        story = []
        story.append(Paragraph("Performance by Play", self.styles['SectionHeading']))

        # Get player's shots by play
        shots = ShotEvent.query.filter_by(player_name=player.name).all()

        plays_performance = {}
        for shot in shots:
            if shot.play_id:
                play_name = shot.play.name if shot.play else f"Play {shot.play_id}"
                if play_name not in plays_performance:
                    plays_performance[play_name] = {
                        'shots': 0,
                        'made': 0,
                        'points': 0
                    }
                plays_performance[play_name]['shots'] += 1
                if shot.result == 'made':
                    plays_performance[play_name]['made'] += 1
                    plays_performance[play_name]['points'] += shot.points

        if not plays_performance:
            story.append(Paragraph("No play data available.", self.styles['CustomBodyText']))
            return story

        plays_data = [['Play', 'Shots', 'Made', 'FG%', 'Points']]
        for play_name, perf in plays_performance.items():
            fg_pct = (perf['made'] / perf['shots'] * 100) if perf['shots'] > 0 else 0
            plays_data.append([
                play_name[:20],  # Truncate long names
                str(perf['shots']),
                str(perf['made']),
                f"{fg_pct:.1f}%",
                str(perf['points'])
            ])

        plays_table = Table(plays_data, colWidths=[1.8 * self.inch, 0.9 * self.inch, 0.9 * self.inch, 0.9 * self.inch, 0.9 * self.inch])
        plays_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors.HexColor('#208dd1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BACKGROUND', (0, 1), (-1, -1), self.colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, self.colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8)
        ]))
        story.append(plays_table)
        return story

    def _generate_player_shot_by_play_analysis(self, player):
        """Generate shot type analysis by play."""
        from reportlab.platypus import Table, TableStyle, Paragraph
        
        story = []
        story.append(Paragraph("Shot Breakdown", self.styles['SectionHeading']))

        shots = ShotEvent.query.filter_by(player_name=player.name).all()

        # Group by shot type
        shot_types = {}
        for shot in shots:
            shot_type = shot.shot_type or 'Unknown'
            if shot_type not in shot_types:
                shot_types[shot_type] = {'total': 0, 'made': 0}
            shot_types[shot_type]['total'] += 1
            if shot.result == 'made':
                shot_types[shot_type]['made'] += 1

        shot_data = [['Shot Type', 'Attempts', 'Made', 'FG%']]
        for shot_type, data in shot_types.items():
            fg_pct = (data['made'] / data['total'] * 100) if data['total'] > 0 else 0
            shot_data.append([
                shot_type,
                str(data['total']),
                str(data['made']),
                f"{fg_pct:.1f}%"
            ])

        shot_table = Table(shot_data, colWidths=[1.5 * self.inch, 1.5 * self.inch, 1.5 * self.inch, 1.5 * self.inch])
        shot_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors.HexColor('#208dd1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, self.colors.black)
        ]))
        story.append(shot_table)
        return story

    def _generate_player_recent_games(self, player):
        """Generate recent games summary."""
        from reportlab.platypus import Table, TableStyle, Paragraph
        
        story = []
        story.append(Paragraph("Recent Games", self.styles['SectionHeading']))

        # Get recent games with this player's shots
        shots = ShotEvent.query.filter_by(player_name=player.name).all()
        game_ids = list(set([s.game_id for s in shots]))[-5:]  # Last 5 games

        games = Game.query.filter(Game.id.in_(game_ids)).order_by(Game.date.desc()).all()

        games_data = [['Date', 'Opponent', 'Shots', 'Made', 'Points', 'Result']]
        for game in games:
            game_shots = [s for s in shots if s.game_id == game.id]
            made = sum(1 for s in game_shots if s.result == 'made')
            points = sum(s.points for s in game_shots if s.result == 'made')
            result = 'W' if game.team_score > game.opponent_score else 'L'
            game_date = game.date.strftime('%m/%d/%Y') if hasattr(game.date, 'strftime') else str(game.date)
            games_data.append([
                game_date,
                game.opponent,
                str(len(game_shots)),
                str(made),
                str(points),
                result
            ])

        games_table = Table(games_data, colWidths=[1 * self.inch, 1.2 * self.inch, 0.8 * self.inch, 0.8 * self.inch, 0.8 * self.inch, 0.6 * self.inch])
        games_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors.HexColor('#208dd1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 1, self.colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8)
        ]))
        story.append(games_table)
        return story

    # ============ Helper Methods for Team ============

    def _calculate_team_stats(self):
        """Calculate team statistics."""
        games = Game.query.all()
        total_games = len(games)
        wins = sum(1 for g in games if g.team_score > g.opponent_score)
        losses = total_games - wins
        total_points_for = sum(g.team_score for g in games)
        total_points_against = sum(g.opponent_score for g in games)
        avg_ppg = total_points_for / total_games if total_games > 0 else 0
        avg_ppg_allowed = total_points_against / total_games if total_games > 0 else 0

        return {
            'total_games': total_games,
            'wins': wins,
            'losses': losses,
            'win_pct': (wins / total_games * 100) if total_games > 0 else 0,
            'total_points': total_points_for,
            'ppg': avg_ppg,
            'ppg_allowed': avg_ppg_allowed
        }

    def _create_team_summary_table(self, stats):
        """Create team summary table."""
        from reportlab.platypus import Table, TableStyle
        
        stats_data = [
            ['Metric', 'Value'],
            ['Games Played', str(stats['total_games'])],
            ['Wins', str(stats['wins'])],
            ['Losses', str(stats['losses'])],
            ['Win %', f"{stats['win_pct']:.1f}%"],
            ['PPG', f"{stats['ppg']:.1f}"],
            ['PPG Allowed', f"{stats['ppg_allowed']:.1f}"],
        ]

        table = Table(stats_data, colWidths=[2.5 * self.inch, 1.5 * self.inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors.HexColor('#208dd1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, self.colors.black)
        ]))
        return table

    def _generate_team_plays_analysis(self):
        """Generate team-wide plays analysis."""
        from reportlab.platypus import Table, TableStyle, Paragraph
        
        story = []
        story.append(Paragraph("Team Plays Analysis", self.styles['SectionHeading']))

        # Get all plays used
        shots = ShotEvent.query.all()
        plays_stats = {}

        for shot in shots:
            if shot.play_id:
                play_name = shot.play.name if shot.play else f"Play {shot.play_id}"
                if play_name not in plays_stats:
                    plays_stats[play_name] = {'shots': 0, 'made': 0}
                plays_stats[play_name]['shots'] += 1
                if shot.result == 'made':
                    plays_stats[play_name]['made'] += 1

        if not plays_stats:
            story.append(Paragraph("No play data available.", self.styles['CustomBodyText']))
            return story

        # Sort by attempts
        sorted_plays = sorted(plays_stats.items(), key=lambda x: x[1]['shots'], reverse=True)[:10]

        plays_data = [['Play', 'Attempts', 'Made', 'FG%']]
        for play_name, data in sorted_plays:
            fg_pct = (data['made'] / data['shots'] * 100) if data['shots'] > 0 else 0
            plays_data.append([
                play_name[:20],
                str(data['shots']),
                str(data['made']),
                f"{fg_pct:.1f}%"
            ])

        plays_table = Table(plays_data, colWidths=[2 * self.inch, 1.2 * self.inch, 1.2 * self.inch, 1.2 * self.inch])
        plays_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors.HexColor('#208dd1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BACKGROUND', (0, 1), (-1, -1), self.colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, self.colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8)
        ]))
        story.append(plays_table)
        return story

    def _generate_team_player_summary(self):
        """Generate team player performance summary."""
        from reportlab.platypus import Table, TableStyle, Paragraph
        
        story = []
        story.append(Paragraph("Top Performers", self.styles['SectionHeading']))

        shots = ShotEvent.query.all()
        player_stats = {}

        for shot in shots:
            player_name = shot.player_name
            if player_name not in player_stats:
                player_stats[player_name] = {'shots': 0, 'made': 0, 'points': 0}
            player_stats[player_name]['shots'] += 1
            if shot.result == 'made':
                player_stats[player_name]['made'] += 1
                player_stats[player_name]['points'] += shot.points

        # Sort by points
        sorted_players = sorted(player_stats.items(), key=lambda x: x[1]['points'], reverse=True)[:10]

        players_data = [['Player', 'Points', 'Shots', 'Made', 'FG%']]
        for player_name, data in sorted_players:
            fg_pct = (data['made'] / data['shots'] * 100) if data['shots'] > 0 else 0
            players_data.append([
                player_name[:15],
                str(data['points']),
                str(data['shots']),
                str(data['made']),
                f"{fg_pct:.1f}%"
            ])

        players_table = Table(players_data, colWidths=[1.2 * self.inch, 1 * self.inch, 1 * self.inch, 1 * self.inch, 1 * self.inch])
        players_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors.HexColor('#208dd1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BACKGROUND', (0, 1), (-1, -1), self.colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, self.colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8)
        ]))
        story.append(players_table)
        return story

    def _generate_plays_effectiveness(self):
        """Generate plays effectiveness analysis."""
        from reportlab.platypus import Table, TableStyle, Paragraph
        
        story = []
        story.append(Paragraph("Plays Effectiveness Ranking", self.styles['SectionHeading']))

        shots = ShotEvent.query.all()
        plays_effectiveness = {}

        for shot in shots:
            if shot.play_id:
                play_name = shot.play.name if shot.play else f"Play {shot.play_id}"
                if play_name not in plays_effectiveness:
                    plays_effectiveness[play_name] = {'shots': 0, 'made': 0}
                plays_effectiveness[play_name]['shots'] += 1
                if shot.result == 'made':
                    plays_effectiveness[play_name]['made'] += 1

        # Sort by FG% (minimum 5 attempts)
        ranked_plays = [
            (name, data) for name, data in plays_effectiveness.items()
            if data['shots'] >= 5
        ]
        ranked_plays.sort(key=lambda x: (x[1]['made'] / x[1]['shots']), reverse=True)

        effectiveness_data = [['Rank', 'Play', 'Attempts', 'FG%']]
        for rank, (play_name, data) in enumerate(ranked_plays[:15], 1):
            fg_pct = (data['made'] / data['shots'] * 100) if data['shots'] > 0 else 0
            effectiveness_data.append([
                str(rank),
                play_name[:18],
                str(data['shots']),
                f"{fg_pct:.1f}%"
            ])

        effectiveness_table = Table(effectiveness_data, colWidths=[0.6 * self.inch, 2.2 * self.inch, 1 * self.inch, 1 * self.inch])
        effectiveness_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.colors.HexColor('#208dd1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BACKGROUND', (0, 1), (-1, -1), self.colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, self.colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8)
        ]))
        story.append(effectiveness_table)
        return story
