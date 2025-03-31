from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField
from wtforms.validators import DataRequired, Optional, EqualTo
from wtforms.fields import DateField, TimeField
from models import db, User, Task, Message
from flask_socketio import SocketIO, emit, join_room, leave_room
from sqlalchemy import or_
from itertools import groupby
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
socketio = SocketIO(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
online_users = {}

class ProfileForm(FlaskForm):
    first_name = StringField('Имя', validators=[DataRequired()])
    last_name = StringField('Фамилия', validators=[DataRequired()])
    username = StringField('Логин', validators=[DataRequired()])
    bio = TextAreaField('О себе', validators=[Optional()])
    current_password = PasswordField('Текущий пароль', validators=[Optional()])
    new_password = PasswordField('Новый пароль', validators=[
        Optional(), 
        EqualTo('confirm_password', message='Пароли должны совпадать')
    ])
    confirm_password = PasswordField('Повторите пароль', validators=[Optional()])

class TaskForm(FlaskForm):
    text = StringField('Задача', validators=[DataRequired()])
    due_date = DateField('Дата', format='%Y-%m-%d', validators=[Optional()])
    due_time = TimeField('Время', validators=[Optional()])

class ChatForm(FlaskForm):
    username = StringField('Логин пользователя', validators=[DataRequired()])

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.route('/')
@login_required
def index():
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.due_date).all()
    form = TaskForm()
    return render_template('index.html', tasks=tasks, form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        
        flash('Неверный логин или пароль!', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        
        if User.query.filter_by(username=username).first():
            flash('Этот логин уже занят!', 'danger')
            return redirect(url_for('register'))
        
        user = User(
            username=username,
            first_name=first_name,
            last_name=last_name
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        flash('Регистрация прошла успешно!', 'success')
        return redirect(url_for('index'))
    
    return render_template('register.html')
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        username=current_user.username,
        bio=current_user.bio or ''
    )

    if form.validate_on_submit():
        current_user.first_name = form.first_name.data
        current_user.last_name = form.last_name.data
        current_user.username = form.username.data
        current_user.bio = form.bio.data
        
        if form.current_password.data:
            if not current_user.check_password(form.current_password.data):
                flash('Текущий пароль неверен', 'danger')
                return redirect(url_for('profile'))
            
            if form.new_password.data:
                current_user.set_password(form.new_password.data)
                flash('Пароль успешно изменен', 'success')
        
        db.session.commit()
        flash('Профиль обновлен', 'success')
        return redirect(url_for('profile'))
    
    return render_template('profile.html', form=form) 

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        online_users[current_user.id] = request.sid
        emit('user_status', {'user_id': current_user.id, 'status': 'online'}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        online_users.pop(current_user.id, None)
        emit('user_status', {'user_id': current_user.id, 'status': 'offline'}, broadcast=True)

@socketio.on('private_message')
def handle_private_message(data):
    if not current_user.is_authenticated:
        return

    recipient_username = data.get('recipient')
    message_text = data.get('message', '').strip()
    
    if not message_text:
        return

    recipient = User.query.filter_by(username=recipient_username).first()
    if not recipient:
        return
    
    message = Message(
        text=message_text,
        sender_id=current_user.id,
        recipient_id=recipient.id
    )
    db.session.add(message)
    db.session.commit()
    
    if recipient.id in online_users:
        emit('new_message', {
            'sender': current_user.username,
            'message': message_text,
            'timestamp': datetime.utcnow().strftime('%H:%M %d.%m.%Y'),
            'sender_id': current_user.id
        }, room=online_users[recipient.id])
        emit('update_unread', {
            'sender_id': current_user.id,
            'count': recipient.get_unread_count(current_user.id)
        }, room=online_users[recipient.id])
    
    emit('message_sent', {
        'recipient': recipient.username,
        'message': message_text
    })

@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    form = ChatForm()
    
    if form.validate_on_submit():
        recipient = User.query.filter_by(username=form.username.data).first()
        if not recipient:
            flash('Пользователь не найден', 'danger')
            return redirect(url_for('chat'))
        
        if recipient.id == current_user.id:
            flash('Нельзя отправить сообщение самому себе', 'danger')
            return redirect(url_for('chat'))
        
        return redirect(url_for('chat_with', username=recipient.username))
    
    last_chats = db.session.query(Message).filter(
        or_(
            Message.sender_id == current_user.id,
            Message.recipient_id == current_user.id
        )
    ).order_by(Message.timestamp.desc()).limit(10).all()
    
    unique_users = set()
    for chat in last_chats:
        if chat.sender_id == current_user.id:
            unique_users.add(chat.recipient)
        else:
            unique_users.add(chat.sender)
    
    return render_template('chat.html', 
                         form=form, 
                         last_chats=unique_users, 
                         online_users=online_users,
                         current_user=current_user)

@app.route('/chat/<username>', methods=['GET', 'POST'])
@login_required
def chat_with(username):
    recipient = User.query.filter_by(username=username).first()
    if not recipient:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('chat'))
    
    form = ChatForm()
    
    messages = db.session.query(Message).filter(
        ((Message.sender_id == current_user.id) & (Message.recipient_id == recipient.id)) |
        ((Message.sender_id == recipient.id) & (Message.recipient_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()
    
    grouped_messages = []
    for date, group in groupby(messages, key=lambda m: m.timestamp.date()):
        grouped_messages.append((date, list(group)))
    
    unread_messages = [msg for msg in messages 
                      if msg.recipient_id == current_user.id and not msg.read]
    for msg in unread_messages:
        msg.read = True
    db.session.commit()
    
    if unread_messages and recipient.id in online_users:
        socketio.emit('messages_read', {
            'reader_id': current_user.id,
            'sender_id': recipient.id
        }, room=online_users[recipient.id])
    
    return render_template('chat_with.html', 
                         recipient=recipient, 
                         messages=grouped_messages,
                         form=form,
                         online_users=online_users)

@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    form = TaskForm()
    if form.validate_on_submit():
        due_date = None
        if form.due_date.data and form.due_time.data:
            due_date = datetime.combine(form.due_date.data, form.due_time.data)
        
        task = Task(
            text=form.text.data,
            due_date=due_date,
            user_id=current_user.id
        )
        db.session.add(task)
        db.session.commit()
        flash('Задача добавлена', 'success')
    return redirect(url_for('index'))

@app.route('/edit_task/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = db.session.get(Task, task_id)
    if not task or task.user_id != current_user.id:
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))

    form = TaskForm()
    if request.method == 'GET':
        form.text.data = task.text
        if task.due_date:
            form.due_date.data = task.due_date.date()
            form.due_time.data = task.due_date.time()

    if form.validate_on_submit():
        task.text = form.text.data
        if form.due_date.data and form.due_time.data:
            task.due_date = datetime.combine(form.due_date.data, form.due_time.data)
        else:
            task.due_date = None
        
        db.session.commit()
        flash('Задача обновлена', 'success')
        return redirect(url_for('index'))

    return render_template('edit_task.html', form=form, task=task)

@app.route('/done/<int:task_id>')
@login_required
def mark_done(task_id):
    task = db.session.get(Task, task_id)
    if task and task.user_id == current_user.id:
        task.done = not task.done
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:task_id>')
@login_required
def delete_task(task_id):
    task = db.session.get(Task, task_id)
    if task and task.user_id == current_user.id:
        db.session.delete(task)
        db.session.commit()
        flash('Задача удалена', 'success')
    return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.first():
            user = User(
                username='test',
                first_name='Test',
                last_name='User',
                bio='Test user'
            )
            user.set_password('test')
            db.session.add(user)
            db.session.commit()
    
    socketio.run(app, debug=True)