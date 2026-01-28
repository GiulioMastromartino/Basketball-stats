from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from core import db
from core.models import Play, PlayType

plays_bp = Blueprint('plays', __name__)

@plays_bp.route('/')
@login_required
def list_plays():
    plays = Play.query.all()
    return render_template('plays/index.html', plays=plays)

@plays_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_play():
    # Todo
    return render_template('plays/new.html')
