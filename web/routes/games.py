from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from core import db
from core.models import Game

games_bp = Blueprint('games', __name__)

@games_bp.route('/')
@login_required
def index():
    games = Game.query.order_by(Game.date.desc()).all()
    return render_template('games/index.html', games=games)

@games_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_game():
    if request.method == 'POST':
        # Todo: Implementation
        pass
    return render_template('games/new.html')
