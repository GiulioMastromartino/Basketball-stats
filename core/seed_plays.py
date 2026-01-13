#!/usr/bin/env python3
"""
Seed plays database from Playbook DR 4 - 2025-2026
Populates the plays table with offensive, defensive, and special plays
"""

from core.models import Play, db

PLAYS_DATA = [
    # === OFFENSIVE PLAYS ===
    {
        "name": "Horns Twist",
        "description": "Pick and roll from horns position. Guard receives screen from top of key, rolls/pops for scoring opportunity.",
        "play_type": "Offense"
    },
    {
        "name": "Spain PNR",
        "description": "Guard initiates pick and roll in Spain position (wing). Ballhandler attacks middle or wing.",
        "play_type": "Offense"
    },
    {
        "name": "Dribble Handoff",
        "description": "Guard executes dribble handoff with wing player. Creates driving lane or passing option.",
        "play_type": "Offense"
    },
    {
        "name": "Pick and Pop",
        "description": "Guard uses screener who pops to mid-range/three-point line after setting screen.",
        "play_type": "Offense"
    },
    {
        "name": "Pick and Roll",
        "description": "Classic pick and roll with ballhandler. Screener rolls to basket or pops for shot.",
        "play_type": "Offense"
    },
    {
        "name": "High Post Entry",
        "description": "Feed post player at high post. Creates passing opportunities to cutters or post scoring.",
        "play_type": "Offense"
    },
    {
        "name": "Wing Isolation",
        "description": "Isolate wing player on one side with screening action. Creates one-on-one opportunity.",
        "play_type": "Offense"
    },
    {
        "name": "Weak Side Cut",
        "description": "Offensive player cuts to basket on weak side while ball is on opposite side. Reverse entry or kick-out pass.",
        "play_type": "Offense"
    },
    {
        "name": "Ball Screen",
        "description": "On-ball screen from guard or wing. Creates separation for shot or driving lane.",
        "play_type": "Offense"
    },
    {
        "name": "Flare Screen",
        "description": "Screener sets screen to create space on perimeter for three-point shot.",
        "play_type": "Offense"
    },
    {
        "name": "Staggered Screen",
        "description": "Two defenders screen consecutively for offensive player. Creates spacing and shooting opportunity.",
        "play_type": "Offense"
    },
    {
        "name": "Cross Screen",
        "description": "Screener crosses lane to set screen on opposite side. Targets post player or wing.",
        "play_type": "Offense"
    },
    {
        "name": "UCLA Cut",
        "description": "Post player screens for wing, wing cuts to basket. High-low action.",
        "play_type": "Offense"
    },
    {
        "name": "Zipper Cut",
        "description": "Cutter uses screen to move along baseline or through lane. Creates backdoor opportunity.",
        "play_type": "Offense"
    },
    {
        "name": "Back Screen",
        "description": "Screener sets screen on defender away from ball. Off-ball movement creates drive or cut opportunity.",
        "play_type": "Offense"
    },
    {
        "name": "Down Screen",
        "description": "Screener sets screen for player on perimeter moving down from top. Creates shot opportunity.",
        "play_type": "Offense"
    },
    {
        "name": "Transition Offense",
        "description": "Fast break with numerical advantage. Outlet pass to guards for quick movement up court.",
        "play_type": "Offense"
    },
    {
        "name": "Triangle Offense",
        "description": "Formation of three players creating spacing and passing angles. Promotes ball movement.",
        "play_type": "Offense"
    },
    {
        "name": "Motion Offense",
        "description": "Continuous ball and player movement with series of screens. Creates open shots through spacing.",
        "play_type": "Offense"
    },
    {
        "name": "Spread P&R",
        "description": "Pick and roll with spread floor (shooters on perimeter). Creates driving lane for ballhandler.",
        "play_type": "Offense"
    },
    
    # === DEFENSIVE PLAYS ===
    {
        "name": "Man-to-Man Defense",
        "description": "Each defender guards assigned opponent. Emphasis on staying in front and denying space.",
        "play_type": "Defense"
    },
    {
        "name": "Zone Defense",
        "description": "Defenders guard area rather than individual. Flexible positioning based on ball location.",
        "play_type": "Defense"
    },
    {
        "name": "2-3 Zone",
        "description": "Two defenders on top, three on baseline. Protects paint and discourages driving.",
        "play_type": "Defense"
    },
    {
        "name": "3-2 Zone",
        "description": "Three defenders on top, two on baseline. More perimeter-oriented defense.",
        "play_type": "Defense"
    },
    {
        "name": "1-3-1 Zone",
        "description": "One on top, three in middle, one at baseline. Protects middle and baseline drives.",
        "play_type": "Defense"
    },
    {
        "name": "Box-and-One",
        "description": "Four defenders form box (perimeter), one guards star player man-to-man.",
        "play_type": "Defense"
    },
    {
        "name": "Triangle-and-Two",
        "description": "Three defenders form triangle (zone), two guard opponents man-to-man.",
        "play_type": "Defense"
    },
    {
        "name": "Full Court Press",
        "description": "Aggressive defense across entire court after made basket. Forces turnovers.",
        "play_type": "Defense"
    },
    {
        "name": "Half Court Press",
        "description": "Aggressive defense starting at half court. Creates pressure on ball handler.",
        "play_type": "Defense"
    },
    {
        "name": "Trap and Recover",
        "description": "Two defenders trap ballhandler, remaining players recover to open players.",
        "play_type": "Defense"
    },
    {
        "name": "Screen Coverage",
        "description": "Defenders go over/under screen or switch. Denies space for screened player.",
        "play_type": "Defense"
    },
    {
        "name": "Switch Defense",
        "description": "Defenders switch assignments during screens. Man-to-man continuity maintained.",
        "play_type": "Defense"
    },
    {
        "name": "Drop Coverage",
        "description": "On-ball screener's defender drops back to protect drive. Creates passing lane.",
        "play_type": "Defense"
    },
    {
        "name": "High Coverage",
        "description": "Screen defender stays tight on screener. Limits dribble drive penetration.",
        "play_type": "Defense"
    },
    {
        "name": "Hedging",
        "description": "Screener's defender moves out to contest ballhandler briefly, returns to screener.",
        "play_type": "Defense"
    },
    {
        "name": "Help and Recover",
        "description": "Help defender leaves assignment to block drive, recovers to original player.",
        "play_type": "Defense"
    },
    {
        "name": "Deny Ball Handler",
        "description": "Defense forces ballhandler away from preferred side/action.",
        "play_type": "Defense"
    },
    {
        "name": "Weak Side Rotation",
        "description": "Defense rotates to help on penetration, weak side stays ready for kick-out.",
        "play_type": "Defense"
    },
    {
        "name": "Transition Defense",
        "description": "Quick defensive setup after turnover or made basket. Stops fast break.",
        "play_type": "Defense"
    },
    {
        "name": "Rebounding Position",
        "description": "Boxout opponent and establish position for rebound. Collective team effort.",
        "play_type": "Defense"
    },
    
    # === SPECIAL PLAYS / ATO (Against the Press) ===
    {
        "name": "Inbound from Sideline",
        "description": "Inbound play from sideline with screening action to break defense and create scoring opportunity.",
        "play_type": "Special"
    },
    {
        "name": "Inbound from Baseline",
        "description": "Inbound play from baseline with cuts and screens to generate open shot or layup.",
        "play_type": "Special"
    },
    {
        "name": "Against Full Court Press",
        "description": "Offensive setup to break full court press. Outlets and spacing to advance ball.",
        "play_type": "Special"
    },
    {
        "name": "Against Half Court Press",
        "description": "Offensive setup to beat half court aggressive defense. Quick passes and movement.",
        "play_type": "Special"
    },
    {
        "name": "Baseline Out of Bounds",
        "description": "Inbound from baseline after timeout or dead ball. Creates quick scoring opportunity.",
        "play_type": "Special"
    },
    {
        "name": "Sideline Out of Bounds",
        "description": "Inbound from sideline timeout. Multiple screening options for desired scorer.",
        "play_type": "Special"
    },
    {
        "name": "Backdoor Cut",
        "description": "Player cuts to basket when defense overplays perimeter. Quick inbound for layup.",
        "play_type": "Special"
    },
    {
        "name": "Lob Play",
        "description": "High pass to rolling or cutting player for dunk/layup. Athletic finish.",
        "play_type": "Special"
    },
    {
        "name": "Curl to Three",
        "description": "Player curls off screen, reads defense for three-point shot or drive.",
        "play_type": "Special"
    },
    {
        "name": "Punch Through",
        "description": "Quick pass through tight defense to create advantage. Timing-dependent play.",
        "play_type": "Special"
    },
    {
        "name": "Elevator Door",
        "description": "Two post players set parallel screens. Guard uses screens to create space for shot.",
        "play_type": "Special"
    },
    {
        "name": "Pick Pocket",
        "description": "Set play to create turnover or steal opportunity. Aggressive defensive action.",
        "play_type": "Special"
    },
    {
        "name": "Crash Boards",
        "description": "Aggressive rebounding play. Multiple bodies attack glass for offensive rebound.",
        "play_type": "Special"
    },
    {
        "name": "Short Clock",
        "description": "Quick scoring play when shot clock is running low. Immediate shot opportunity.",
        "play_type": "Special"
    },
    {
        "name": "Game Winner",
        "description": "Final possession play design. Creates best shot with seconds remaining.",
        "play_type": "Special"
    },
]


def seed_plays():
    """
    Populate the plays table with predefined plays.
    """
    try:
        # Check if plays already exist
        existing_count = Play.query.count()
        if existing_count > 0:
            print(f"[SEED] {existing_count} plays already in database. Skipping seed.")
            return

        print(f"[SEED] Adding {len(PLAYS_DATA)} plays to database...")
        for play_data in PLAYS_DATA:
            play = Play(
                name=play_data["name"],
                description=play_data["description"],
                play_type=play_data["play_type"]
            )
            db.session.add(play)

        db.session.commit()
        print(f"[SEED] Successfully added {len(PLAYS_DATA)} plays!")
    except Exception as e:
        db.session.rollback()
        print(f"[SEED] Error seeding plays: {e}")
