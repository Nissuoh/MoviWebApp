"""Exercise the required routes using a separate temporary SQLite database."""
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from sqlalchemy.exc import SQLAlchemyError

from app import create_app, fetch_movie, MovieLookupError
from data_manager import DataManager
from models import db

OMDB_FILM = {'Response': 'True', 'Title': 'Inception', 'Director': 'Christopher Nolan', 'Year': '2010', 'Poster': 'https://example.org/poster.jpg', 'imdbID': 'tt1375666'}


class MovieAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='moviweb-tests-')
        self.database = Path(self.tmp.name) / 'tests.db'
        self.config = {'TESTING': True, 'SECRET_KEY': 'test-only-secret', 'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(self.database), 'OMDB_API_KEY': 'test-only-key'}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.manager = DataManager()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.tmp.cleanup()

    def token(self):
        html = self.client.get('/').get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def post(self, path, fields=None):
        data = dict(fields or {})
        data['csrf_token'] = self.token()
        return self.client.post(path, data=data)

    def user(self, name='Test Nutzer'):
        response = self.post('/users', {'name': name})
        self.assertEqual(response.status_code, 303)
        with self.app.app_context():
            return self.manager.get_users()[-1].id

    def add_film(self, user_id):
        fake = Mock()
        fake.json.return_value = dict(OMDB_FILM)
        with patch('app.requests.get', return_value=fake) as get:
            response = self.post(f'/users/{user_id}/movies', {'title': 'Inception'})
            get.assert_called_once_with('https://www.omdbapi.com/', params={'apikey': 'test-only-key', 't': 'Inception', 'type': 'movie'}, timeout=10)
        self.assertEqual(response.status_code, 303)
        with self.app.app_context():
            return self.manager.get_movies(user_id)[-1].id

    def test_create_list_users_unicode_and_html_escape(self):
        uid = self.user('  Zoë <script>alert(1)</script>  ')
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('Zoë &lt;script&gt;', html)
        self.assertNotIn('<script>alert', html)
        self.assertIn(f'/users/{uid}/movies', html)
        self.assertEqual(self.client.get('/users').status_code, 200)

    def test_reject_blank_and_long_user_names(self):
        for name in ('   ', 'x' * 101):
            self.assertEqual(self.post('/users', {'name': name}).status_code, 400)
        with self.app.app_context():
            self.assertEqual(self.manager.get_users(), [])

    def test_movie_crud_and_omdb_metadata(self):
        uid = self.user()
        mid = self.add_film(uid)
        html = self.client.get(f'/users/{uid}/movies').get_data(as_text=True)
        self.assertIn('Inception', html)
        self.assertIn('Christopher Nolan', html)
        self.assertIn('2010', html)
        self.assertIn('https://example.org/poster.jpg', html)
        with patch('app.requests.get') as get:
            response = self.post(f'/users/{uid}/movies/{mid}/update', {'title': '  Eigener korrigierter Titel  '})
            get.assert_not_called()
        self.assertEqual(response.status_code, 303)
        with self.app.app_context():
            movie = self.manager.get_movie(mid)
            self.assertEqual(movie.name, 'Eigener korrigierter Titel')
            self.assertEqual(movie.director, 'Christopher Nolan')
        self.assertEqual(self.post(f'/users/{uid}/movies/{mid}/delete').status_code, 303)
        with self.app.app_context():
            self.assertEqual(self.manager.get_movies(uid), [])

    def test_movies_persist_across_app_restart(self):
        uid = self.user()
        self.add_film(uid)
        restarted = create_app(self.config)
        html = restarted.test_client().get(f'/users/{uid}/movies').get_data(as_text=True)
        self.assertIn('Inception', html)
        with restarted.app_context():
            db.session.remove()
            db.engine.dispose()

    def test_other_users_cannot_update_or_delete_movie(self):
        owner = self.user('Alice')
        other = self.user('Bob')
        mid = self.add_film(owner)
        self.assertNotIn('Inception', self.client.get(f'/users/{other}/movies').get_data(as_text=True))
        self.assertEqual(self.post(f'/users/{other}/movies/{mid}/update', {'title': 'Changed'}).status_code, 404)
        self.assertEqual(self.post(f'/users/{other}/movies/{mid}/delete').status_code, 404)
        with self.app.app_context():
            self.assertEqual(self.manager.get_movie(mid).name, 'Inception')

    def test_invalid_csrf_is_rejected(self):
        self.assertEqual(self.client.post('/users', data={'name': 'Bad'}).status_code, 400)
        self.assertEqual(self.client.post('/users', data={'name': 'Bad', 'csrf_token': 'wrong'}).status_code, 400)
        with self.app.app_context():
            self.assertEqual(self.manager.get_users(), [])

    def test_unknown_resources_return_404_template(self):
        for path in ('/missing', '/users/9999/movies'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404)
            self.assertIn('404', response.get_data(as_text=True))
        uid = self.user()
        self.assertEqual(self.post(f'/users/{uid}/movies/9999/update', {'title': 'X'}).status_code, 404)
        self.assertEqual(self.post('/users/9999/movies', {'title': 'X'}).status_code, 404)

    def test_delete_requires_post(self):
        uid = self.user()
        mid = self.add_film(uid)
        self.assertEqual(self.client.get(f'/users/{uid}/movies/{mid}/delete').status_code, 405)
        with self.app.app_context():
            self.assertIsNotNone(self.manager.get_movie(mid))

    def test_missing_api_key_is_an_explicit_setup_error(self):
        uid = self.user()
        self.app.config['OMDB_API_KEY'] = ''
        with patch('app.requests.get') as get:
            response = self.post(f'/users/{uid}/movies', {'title': 'Inception'})
            get.assert_not_called()
        self.assertEqual(response.status_code, 503)
        self.assertIn('OMDB_API_KEY', response.get_data(as_text=True))

    def test_movie_not_found_and_network_timeout(self):
        uid = self.user()
        fake = Mock()
        fake.json.return_value = {'Response': 'False', 'Error': 'Movie not found!'}
        with patch('app.requests.get', return_value=fake):
            self.assertEqual(self.post(f'/users/{uid}/movies', {'title': 'Unknown'}).status_code, 404)
        with patch('app.requests.get', side_effect=requests.Timeout('fixture timeout')):
            self.assertEqual(self.post(f'/users/{uid}/movies', {'title': 'Inception'}).status_code, 502)
        with self.app.app_context():
            self.assertEqual(self.manager.get_movies(uid), [])

    def test_malformed_omdb_payload_and_missing_metadata(self):
        fake = Mock()
        for payload in ([], {'Response': 'True', 'Title': ''}):
            fake.json.return_value = payload
            with patch('app.requests.get', return_value=fake):
                with self.assertRaises(MovieLookupError):
                    fetch_movie('X', 'test-only-key')
        fake.json.return_value = {'Response': 'True', 'Title': 'Unknown year', 'Year': 'N/A', 'Poster': 'N/A'}
        with patch('app.requests.get', return_value=fake):
            info = fetch_movie('X', 'test-only-key')
        self.assertIsNone(info['year'])
        self.assertIsNone(info['poster_url'])

    def test_blank_movie_titles_do_not_call_omdb(self):
        uid = self.user()
        mid = self.add_film(uid)
        with patch('app.requests.get') as get:
            self.assertEqual(self.post(f'/users/{uid}/movies', {'title': '  '}).status_code, 400)
            self.assertEqual(self.post(f'/users/{uid}/movies/{mid}/update', {'title': '  '}).status_code, 400)
            get.assert_not_called()
        with self.app.app_context():
            self.assertEqual(self.manager.get_movie(mid).name, 'Inception')

    def test_duplicate_movie_is_reported_without_second_record(self):
        uid = self.user()
        self.add_film(uid)
        fake = Mock()
        fake.json.return_value = dict(OMDB_FILM)
        with patch('app.requests.get', return_value=fake):
            response = self.post(f'/users/{uid}/movies', {'title': 'Inception'})
        self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            self.assertEqual(len(self.manager.get_movies(uid)), 1)

    def test_database_commit_failure_rolls_back(self):
        uid = self.user('Existing')
        with patch.object(db.session, 'commit', side_effect=SQLAlchemyError('fixture failure')):
            self.assertEqual(self.post('/users', {'name': 'Should roll back'}).status_code, 500)
        with self.app.app_context():
            users = self.manager.get_users()
            self.assertEqual([(user.id, user.name) for user in users], [(uid, 'Existing')])
        self.user('Works after rollback')


if __name__ == '__main__':
    unittest.main()
