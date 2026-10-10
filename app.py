"""MoviWeb: select a user and manage their favourite films."""
import os
import re
import secrets
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import SQLAlchemyError

from data_manager import DataManager
from models import db, Movie

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')


class MovieLookupError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def fetch_movie(title, api_key):
    """Query OMDb on the server; never put the key into HTML or logs."""
    if not api_key:
        raise MovieLookupError('OMDb ist noch nicht eingerichtet. Bitte OMDB_API_KEY in .env setzen.', 503)
    try:
        response = requests.get('https://www.omdbapi.com/', params={'apikey': api_key, 't': title, 'type': 'movie'}, timeout=10)
        response.raise_for_status()
        info = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise MovieLookupError('OMDb ist momentan nicht erreichbar. Bitte später erneut versuchen.') from exc
    if not isinstance(info, dict):
        raise MovieLookupError('OMDb hat eine ungültige Antwort geliefert.')
    if info.get('Response') != 'True':
        if info.get('Error') == 'Movie not found!':
            raise MovieLookupError('Kein Film zu diesem Titel gefunden.', 404)
        raise MovieLookupError('OMDb konnte den Film nicht laden. Bitte API-Konfiguration prüfen.')
    name = str(info.get('Title') or '').strip()
    if not name or len(name) > 200:
        raise MovieLookupError('OMDb hat keinen gültigen Filmtitel geliefert.')
    year_match = re.match(r'^[0-9]{4}', str(info.get('Year', '')))
    poster = str(info.get('Poster') or '')
    return {
        'name': name,
        'director': str(info.get('Director') or 'N/A')[:300],
        'year': int(year_match.group(0)) if year_match else None,
        'poster_url': poster if poster.startswith('https://') else None,
        'imdb_id': str(info.get('imdbID') or '')[:30] or None,
    }


def create_app(config=None):
    app = Flask(__name__)
    data_dir = BASE_DIR / 'data'
    data_dir.mkdir(exist_ok=True)
    app.config.update(
        SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),
        SQLALCHEMY_DATABASE_URI='sqlite:///' + str(data_dir / 'movies.db'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        OMDB_API_KEY=os.environ.get('OMDB_API_KEY') or os.environ.get('OMDB_KEY', ''),
        MAX_CONTENT_LENGTH=1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
    )
    if config:
        app.config.update(config)
    db.init_app(app)
    manager = DataManager()

    def csrf_token():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(32)
        return session['csrf_token']

    app.jinja_env.globals['csrf_token'] = csrf_token

    @app.before_request
    def validate_form_token():
        if request.method == 'POST':
            expected = session.get('csrf_token', '')
            provided = request.form.get('csrf_token', '')
            if not expected or not secrets.compare_digest(expected, provided):
                abort(400, description='Formular abgelaufen. Bitte Seite neu laden und erneut senden.')

    def require_user(user_id):
        user = manager.get_user(user_id)
        if user is None:
            abort(404)
        return user

    def movies_page(user_id, error=None, status=200):
        user = require_user(user_id)
        return render_template('movies.html', user=user, movies=manager.get_movies(user_id), error=error), status

    @app.get('/')
    @app.get('/users')
    def index():
        return render_template('index.html', users=manager.get_users())

    @app.post('/users')
    def create_user():
        try:
            manager.create_user(request.form.get('name', ''))
        except ValueError as exc:
            return render_template('index.html', users=manager.get_users(), error=str(exc)), 400
        flash('Nutzer angelegt.')
        return redirect(url_for('index'), code=303)

    @app.get('/users/<int:user_id>/movies')
    def get_movies(user_id):
        return movies_page(user_id)

    @app.post('/users/<int:user_id>/movies')
    def add_movie(user_id):
        require_user(user_id)
        title = request.form.get('title', '').strip()
        if not title or len(title) > 200:
            return movies_page(user_id, 'Bitte einen Filmtitel mit 1 bis 200 Zeichen eingeben.', 400)
        try:
            info = fetch_movie(title, app.config['OMDB_API_KEY'])
            manager.add_movie(Movie(user_id=user_id, **info))
        except MovieLookupError as exc:
            return movies_page(user_id, str(exc), exc.status)
        except ValueError as exc:
            return movies_page(user_id, str(exc), 400)
        flash('Film hinzugefügt.')
        return redirect(url_for('get_movies', user_id=user_id), code=303)

    @app.post('/users/<int:user_id>/movies/<int:movie_id>/update')
    def update_movie(user_id, movie_id):
        require_user(user_id)
        if manager.get_movie(movie_id, user_id) is None:
            abort(404)
        try:
            manager.update_movie(movie_id, request.form.get('title', ''), user_id)
        except ValueError as exc:
            return movies_page(user_id, str(exc), 400)
        flash('Filmtitel aktualisiert.')
        return redirect(url_for('get_movies', user_id=user_id), code=303)

    @app.post('/users/<int:user_id>/movies/<int:movie_id>/delete')
    def delete_movie(user_id, movie_id):
        require_user(user_id)
        if manager.get_movie(movie_id, user_id) is None:
            abort(404)
        manager.delete_movie(movie_id, user_id)
        flash('Film entfernt.')
        return redirect(url_for('get_movies', user_id=user_id), code=303)

    @app.errorhandler(404)
    def page_not_found(error):
        return render_template('404.html'), 404

    @app.errorhandler(400)
    @app.errorhandler(405)
    @app.errorhandler(413)
    def client_error(error):
        return render_template('error.html', message=error.description, status=error.code), error.code

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        db.session.rollback()
        app.logger.error('Database operation failed (%s)', type(error).__name__)
        return render_template('error.html', message='Datenbank momentan nicht verfügbar. Bitte erneut versuchen.', status=500), 500

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return render_template('error.html', message='Ein Serverfehler ist aufgetreten.', status=500), 500

    with app.app_context():
        db.create_all()
    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')), debug=False)
