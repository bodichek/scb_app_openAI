# PDF Tables Extractor (Django + Poetry)

This project is a Django web application that:
- Accepts PDF uploads
- Extracts tables using Camelot and pdfplumber
- Cleans and normalizes table data
- Stores data in a database
- Provides a simple dashboard to visualize aggregates via Chart.js

## Quick start

1. Install dependencies:
   - Python 3.10 or 3.11
   - Poetry
   - Ghostscript (for Camelot) and ensure its `bin` directory is on PATH

2. Install project packages:

```sh
poetry install
```

3. Create Django project structure (if not already present) and run migrations:

```sh
poetry run python manage.py makemigrations
poetry run python manage.py migrate
poetry run python manage.py createsuperuser
```

4. Run the development server:

```sh
poetry run python manage.py runserver
```

Visit http://127.0.0.1:8000/ingestion/upload to upload PDFs.

## Notes
- Extraction tries Camelot (lattice then stream). If none found, it falls back to pdfplumber.
- Extracted rows are stored as JSON so tables with varying schemas are supported. For advanced JSON querying consider Postgres.
