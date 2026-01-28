from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from core import db

reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/')
@login_required
def index():
    return render_template('reports/index.html')
