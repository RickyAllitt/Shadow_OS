from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models import Player
from app.extensions import db

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = Player.query.filter_by(name=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('System Access Granted.', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            flash('Access Denied: Invalid Credentials.', 'error')
            
    return render_template('login.html')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm = request.form.get('confirm')
        
        if password != confirm:
            flash('Error: Passwords do not match.', 'error')
            return redirect(url_for('auth.register'))
            
        if Player.query.filter_by(name=username).first():
            flash('Error: Hunter name already taken.', 'error')
            return redirect(url_for('auth.register'))
            
        new_user = Player(name=username)
        new_user.set_password(password)
        
        # Give starting stats
        new_user.level = 1
        new_user.xp = 0
        new_user.xp_required = 100
        new_user.gold = 0
        new_user.title = "E-Rank Hunter"
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration Complete. Welcome, Hunter.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('register.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('System Access Terminated.', 'success')
    return redirect(url_for('auth.login'))

@bp.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    user = current_user
    db.session.delete(user)
    db.session.commit()
    logout_user() # Ensure session is cleared
    flash('Account Deleted. Goodbye, Hunter.', 'success')
    return redirect(url_for('auth.login'))
