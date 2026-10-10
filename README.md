# MoviWebApp

Flask, Flask-SQLAlchemy und SQLite: Nutzer auswählen und deren Lieblingsfilme hinzufügen, auflisten, bearbeiten und entfernen. Neue Filme werden serverseitig über OMDb geladen. Die Auswahl eines Nutzernamens ist die Identitätsauswahl dieser Lernaufgabe; es ist keine Passwortanmeldung.

## Start

1. python3 -m venv venv
2. venv/bin/python -m pip install -r requirements.txt
3. .env.example nach .env kopieren und einen eigenen vorhandenen OMDb-Schlüssel bei OMDB_API_KEY setzen. .env bleibt lokal und wird nicht veröffentlicht. SECRET_KEY kann für unveränderte Sitzungen nach Neustarts gesetzt werden; ohne Angabe erzeugt die App beim Start einen Zufallswert.
4. venv/bin/python app.py
5. Im Codio-Menü Open Flask Application öffnen (Port 5000).

Die SQLite-Datei data/movies.db wird beim ersten Start automatisch angelegt. Vorhandene instance/movies.db aus der Kursumgebung wird nicht überschrieben. Für lokale Tests wird eine separate Datenbank benutzt.

## Pflichtumfang

- models.py: User und Movie, Fremdschlüssel user_id, Filmtitel, Regisseur, Jahr, Poster.
- data_manager.py: create_user, get_users, get_movies, add_movie, update_movie, delete_movie; Commit mit Rollback bei Fehlern.
- app.py: die vorgegebenen GET-/POST-Routen; OMDb mit HTTPS, Timeout und Fehlerbehandlung.
- templates/: gemeinsame Basis, Nutzerliste/Formular, Filmliste mit Formularen, 404 und weitere Fehlerseiten.
- static/style.css: gemeinsames schlichtes Stylesheet. Keine optionalen Design- oder Deployment-Boni.
- Formular-Token, Eingabeprüfung, Escaping und Prüfung der Zuordnung von Film und Nutzer.

## Tests

venv/bin/python -m unittest discover -s tests -v

Die automatisierten OMDb-Fälle verwenden kontrollierte Antworten; sie sind kein Nachweis einer erfolgreichen Live-OMDb-Abfrage. Ein vorhandener gültiger Schlüssel ist für die vollständige Live-Prüfung erforderlich.
