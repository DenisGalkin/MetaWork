from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    bio = db.Column(db.String(500), nullable=True)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    
    tasks = db.relationship('Task', backref='user', lazy=True, cascade='all, delete-orphan')
    sent_messages = db.relationship('Message', 
                                  foreign_keys='Message.sender_id', 
                                  backref='sender', 
                                  lazy=True)
    received_messages = db.relationship('Message', 
                                      foreign_keys='Message.recipient_id', 
                                      backref='recipient', 
                                      lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def is_online(self):
        return (datetime.utcnow() - self.last_seen).total_seconds() < 300

    def get_unread_count(self, sender_id):
        return Message.query.filter_by(
            recipient_id=self.id,
            sender_id=sender_id,
            read=False
        ).count()

    def __repr__(self):
        return f'<User {self.username}>'


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(200), nullable=False)
    done = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<Task {self.text[:20]}>'


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    read = db.Column(db.Boolean, default=False)
    
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def mark_as_read(self):
        if not self.read:
            self.read = True
            db.session.commit()

    def __repr__(self):
        return f'<Message {self.text[:20]}>'