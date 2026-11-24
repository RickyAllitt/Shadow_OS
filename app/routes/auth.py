from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models import Player
from app.extensions import db
from app.services import calculate_xp_required

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
            if user.needs_rehash():
                user.set_password(password)  # Upgrade legacy SHA-256 hash
                db.session.commit()
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
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        confirm = request.form.get('confirm') or ''

        if not username or len(username) > 50:
            flash('Error: Hunter name must be 1-50 characters.', 'error')
            return redirect(url_for('auth.register'))

        if not password:
            flash('Error: Password required.', 'error')
            return redirect(url_for('auth.register'))

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
        new_user.xp_required = calculate_xp_required(1)
        new_user.gold = 0
        # Device timezone (filled in by the browser); the daily reset is 01:00 there
        from app.services import is_valid_timezone, DEFAULT_TIMEZONE
        tz_name = (request.form.get('timezone') or '').strip()
        new_user.timezone = tz_name if is_valid_timezone(tz_name) else DEFAULT_TIMEZONE
        
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
