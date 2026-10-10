"""Keep database reads and writes separate from Flask routes."""
from models import db, User, Movie


class DataManager:
    @staticmethod
    def _commit():
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    def create_user(self, name):
        name = name.strip()
        if not name or len(name) > 100:
            raise ValueError('Bitte einen Namen mit 1 bis 100 Zeichen eingeben.')
        user = User(name=name)
        db.session.add(user)
        self._commit()
        return user

    def get_users(self):
        return db.session.scalars(db.select(User).order_by(User.id)).all()

    def get_user(self, user_id):
        return db.session.get(User, user_id)

    def get_movies(self, user_id):
        return db.session.scalars(db.select(Movie).where(Movie.user_id == user_id).order_by(Movie.id)).all()

    def get_movie(self, movie_id, user_id=None):
        movie = db.session.get(Movie, movie_id)
        if movie is not None and user_id is not None and movie.user_id != user_id:
            return None
        return movie

    def add_movie(self, movie):
        if self.get_user(movie.user_id) is None:
            raise ValueError('Nutzer nicht gefunden.')
        if not movie.name or not movie.name.strip() or len(movie.name) > 200:
            raise ValueError('Bitte einen Filmtitel mit 1 bis 200 Zeichen eingeben.')
        if movie.imdb_id:
            existing = db.session.scalar(db.select(Movie).where(Movie.user_id == movie.user_id, Movie.imdb_id == movie.imdb_id))
            if existing:
                raise ValueError('Dieser Film steht bereits auf deiner Liste.')
        db.session.add(movie)
        self._commit()
        return movie

    def update_movie(self, movie_id, new_title, user_id=None):
        movie = self.get_movie(movie_id, user_id)
        if movie is None:
            raise LookupError('Film nicht gefunden.')
        title = new_title.strip()
        if not title or len(title) > 200:
            raise ValueError('Bitte einen Filmtitel mit 1 bis 200 Zeichen eingeben.')
        movie.name = title
        self._commit()
        return movie

    def delete_movie(self, movie_id, user_id=None):
        movie = self.get_movie(movie_id, user_id)
        if movie is None:
            raise LookupError('Film nicht gefunden.')
        db.session.delete(movie)
        self._commit()
