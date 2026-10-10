"""SQLAlchemy models for users and their favourite movies."""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    movies = db.relationship('Movie', back_populates='user', cascade='all, delete-orphan')


class Movie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    director = db.Column(db.String(300), nullable=False, default='N/A')
    year = db.Column(db.Integer, nullable=True)
    poster_url = db.Column(db.String(1000), nullable=True)
    imdb_id = db.Column(db.String(30), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', back_populates='movies')
    __table_args__ = (db.UniqueConstraint('user_id', 'imdb_id', name='unique_user_imdb'),)
