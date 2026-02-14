import matplotlib
matplotlib.use("Agg")  # Non-GUI backend
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import base64
from io import BytesIO
from sqlalchemy import desc
from core.models import ShotEvent, PlayerStat, Game, db
from core.utils import calculate_possessions, calculate_ortg, parse_minutes

MAX_SHOTS_PER_CHART = 5000  # Safety limit

def generate_shot_chart(player_name, game_ids, db_session=None):
    """
    Generate a basketball shot chart showing make/miss locations
    Returns base64 encoded PNG
    """
    session = db_session or db.session
    
    # Query shot events for this player
    shots = (
        session.query(ShotEvent)
        .filter(ShotEvent.player_name == player_name)
        .filter(ShotEvent.game_id.in_(game_ids))
        .filter(ShotEvent.x_loc.isnot(None))
        .filter(ShotEvent.y_loc.isnot(None))
        .limit(MAX_SHOTS_PER_CHART)
        .all()
    )

    if not shots:
        return ""

    return _create_court_plot(shots)

def generate_team_shot_chart(game_ids, db_session=None):
    """
    Generate team-wide shot chart showing all team shots
    Returns base64 encoded PNG - FIXED DIMENSIONS
    """
    session = db_session or db.session
    
    shots = (
        session.query(ShotEvent)
        .filter(ShotEvent.game_id.in_(game_ids))
        .filter(ShotEvent.x_loc.isnot(None))
        .filter(ShotEvent.y_loc.isnot(None))
        .limit(MAX_SHOTS_PER_CHART)
        .all()
    )

    if not shots:
        return ""

    return _create_court_plot(shots, is_team=True)

def _create_court_plot(shots, is_team=False):
    """Internal helper to plot shots on court"""
    try:
        # Create figure with CORRECT basketball court proportions
        fig, ax = plt.subplots(figsize=(7, 7.5) if is_team else (8, 7.5))

        # Draw basketball court
        line_width = 2.5 if is_team else 2

        ax.plot([0, 500], [0, 0], 'k-', linewidth=line_width)
        ax.plot([0, 500], [470, 470], 'k-', linewidth=line_width)
        ax.plot([0, 0], [0, 470], 'k-', linewidth=line_width)
        ax.plot([500, 500], [0, 470], 'k-', linewidth=line_width)

        # Paint / Key
        paint_width = 163.3
        paint_height = 193.3 if is_team else 193.3 # Same
        paint_x = (500 - paint_width) / 2 # Centered
        paint = patches.Rectangle((paint_x, 0), paint_width, paint_height,
                                  linewidth=line_width, edgecolor='black', facecolor='none')
        ax.add_patch(paint)

        # Free throw circle
        ft_circle = patches.Circle((250, 195.3), 60, linewidth=line_width,
                                   edgecolor='black', facecolor='none')
        ax.add_patch(ft_circle)

        # 3-point arc
        ax.plot([30, 30], [0, 99.7], 'k-', linewidth=line_width)
        ax.plot([470, 470], [0, 99.7], 'k-', linewidth=line_width)
        
        three_pt_arc = patches.Arc((250, 99.7), 440, 440,
                                  theta1=0, theta2=180, linewidth=line_width,
                                  edgecolor='black', facecolor='none')
        ax.add_patch(three_pt_arc)

        # Hoop
        hoop = patches.Circle((250, 52.5), 7.5, linewidth=line_width,
                             edgecolor='black', facecolor='none')
        ax.add_patch(hoop)

        # Backboard
        ax.plot([220, 280], [40, 40], 'k-', linewidth=line_width)

        if is_team:
             # Restricted Area Arc
            restricted_arc = patches.Arc((250, 52.5), 83.32, 83.32,
                                        theta1=0, theta2=180, linewidth=line_width,
                                        edgecolor='black', facecolor='none')
            ax.add_patch(restricted_arc)
            
            # Center Circle
            center_circle = patches.Arc((250, 470), 120, 120, theta1=180, theta2=360,
                                   linewidth=line_width, edgecolor='black', facecolor='none')
            ax.add_patch(center_circle)

        # Plot shots
        makes = [s for s in shots if s.result == 'made']
        misses = [s for s in shots if s.result == 'missed']

        if makes:
            make_x = [s.x_loc for s in makes]
            make_y = [s.y_loc for s in makes]
            ax.scatter(make_x, make_y, c='#28a745', s=60 if is_team else 80, alpha=0.5 if is_team else 0.6,
                      edgecolors='darkgreen', linewidth=1.5, marker='o', label='Made')

        if misses:
            miss_x = [s.x_loc for s in misses]
            miss_y = [s.y_loc for s in misses]
            ax.scatter(miss_x, miss_y, c='#dc3545', s=60 if is_team else 80, alpha=0.5 if is_team else 0.6,
                      edgecolors='darkred', linewidth=1.5, marker='x', label='Missed')

        # Add statistics text
        total_shots = len(shots)
        total_makes = len(makes)
        fg_pct = (total_makes / total_shots * 100) if total_shots > 0 else 0

        if is_team:
            stats_text = f"Team Total: {total_makes}/{total_shots} ({fg_pct:.1f}%)"
            ax.text(250, 490, stats_text, ha='center', va='top',
                   fontsize=11, fontweight='bold',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.9))
        else:
            # Count 2PT vs 3PT
            three_pt_shots = [s for s in shots if s.shot_type == '3pt']
            three_pt_makes = [s for s in three_pt_shots if s.result == 'made']
            three_pct = (len(three_pt_makes) / len(three_pt_shots) * 100) if three_pt_shots else 0

            two_pt_shots = [s for s in shots if s.shot_type == '2pt']
            two_pt_makes = [s for s in two_pt_shots if s.result == 'made']
            two_pct = (len(two_pt_makes) / len(two_pt_shots) * 100) if two_pt_shots else 0
            
            stats_text = f"Overall: {total_makes}/{total_shots} ({fg_pct:.1f}%)\n"
            stats_text += f"2PT: {len(two_pt_makes)}/{len(two_pt_shots)} ({two_pct:.1f}%)\n"
            stats_text += f"3PT: {len(three_pt_makes)}/{len(three_pt_shots)} ({three_pct:.1f}%)"
            
            ax.text(250, 490, stats_text, ha='center', va='top',
                   fontsize=10, bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

        ax.set_xlim(-10, 510)
        ax.set_ylim(-10, 520)
        ax.set_aspect('equal')
        ax.axis('off')
        ax.legend(loc='upper left', fontsize=10 if is_team else 9)

        plt.tight_layout()

        img_io = BytesIO()
        plt.savefig(img_io, format='png', dpi=120, bbox_inches='tight')
        img_io.seek(0)
        img_base64 = base64.b64encode(img_io.read()).decode()
        plt.close(fig)

        return img_base64
    except Exception as e:
        plt.close('all')
        return ""

def generate_player_charts(stats, game_map, player_name):
    """
    Generate charts for player report.
    Plus/Minus chart only includes LIVE game data for accuracy.
    """
    if not stats:
        return {'chart_scoring': '', 'chart_shooting': ''}

    try:
        dates = []
        points = []
        plus_minus_vals = []

        for s in stats:
            game = game_map.get(s.game_id)
            if game:
                dates.append(game.date)
                points.append(s.points)
                
                # Only show +/- for LIVE games
                if game.source == 'LIVE':
                    plus_minus_vals.append(s.plus_minus)
                else:
                    plus_minus_vals.append(None)

        # Scoring Chart with +/
        fig, ax1 = plt.subplots(figsize=(10, 4))
        ax1.bar(dates, points, color='#007bff', alpha=0.6, label='Points')
        ax1.set_ylabel('Points', color='#007bff')

        # Add +/- line on secondary axis (only LIVE games)
        ax2 = ax1.twinx()
        live_dates = [d for d, pm in zip(dates, plus_minus_vals) if pm is not None]
        live_pm = [pm for pm in plus_minus_vals if pm is not None]

        if live_pm:
            ax2.plot(live_dates, live_pm, color='#28a745', marker='o',
                    linewidth=2, label='+/- (LIVE only)', markersize=4)
            ax2.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
            ax2.set_ylabel('+/-', color='#28a745')
            ax2.legend(loc='upper right')

        # Add trend line (MA 3)
        if len(points) >= 3:
            ma3 = [sum(points[i-2:i+1])/3 if i >= 2 else points[i] for i in range(len(points))]
            ax1.plot(dates, ma3, color='#0056b3', linestyle='--', linewidth=2, label='3-Game MA')

        ax1.tick_params(axis='x', rotation=45)
        ax1.legend(loc='upper left')
        plt.title(f"{player_name} - Scoring & +/- Trend")
        plt.tight_layout()

        img_io = BytesIO()
        plt.savefig(img_io, format='png', dpi=100)
        img_io.seek(0)
        chart_scoring = base64.b64encode(img_io.read()).decode()
        plt.close()

        return {'chart_scoring': chart_scoring}
    except Exception:
        plt.close('all')
        return {'chart_scoring': '', 'chart_shooting': ''}

def generate_team_scoring_trend(games):
    """Generate team scoring trend chart"""
    if not games:
        return ""

    try:
        dates = [g.date for g in games]
        team_scores = [g.team_score for g in games]
        opp_scores = [g.opponent_score for g in games]

        fig, ax = plt.subplots(figsize=(10, 5))

        # Plot lines
        ax.plot(range(len(dates)), team_scores, marker='o', label='Team Score',
                color='#28a745', linewidth=2)
        ax.plot(range(len(dates)), opp_scores, marker='s', label='Opponent Score',
                color='#dc3545', linewidth=2, linestyle='--')

        # Add horizontal average lines
        avg_team = sum(team_scores) / len(team_scores)
        avg_opp = sum(opp_scores) / len(opp_scores)
        ax.axhline(y=avg_team, color='#28a745', linestyle=':', alpha=0.5, label=f'Avg Team: {avg_team:.1f}')
        ax.axhline(y=avg_opp, color='#dc3545', linestyle=':', alpha=0.5, label=f'Avg Opp: {avg_opp:.1f}')

        ax.set_xlabel('Game Number', fontsize=10)
        ax.set_ylabel('Points', fontsize=10)
        ax.set_title('Team Scoring Trends', fontsize=12, fontweight='bold')
        ax.legend(fontsize=8, loc='best')
        ax.grid(True, alpha=0.3)

        # Set x-axis
        ax.set_xticks(range(0, len(dates), max(1, len(dates) // 10)))
        ax.set_xticklabels(range(1, len(dates) + 1, max(1, len(dates) // 10)))

        plt.tight_layout()

        img_io = BytesIO()
        plt.savefig(img_io, format='png', dpi=100, bbox_inches='tight')
        img_io.seek(0)
        img_base64 = base64.b64encode(img_io.read()).decode()
        plt.close(fig)

        return img_base64
    except Exception:
        plt.close('all')
        return ""
