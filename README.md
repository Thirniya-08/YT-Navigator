
**How it fits together:** 

The application is structured as a Django web service (Django 5.1) running behind Gunicorn. Requests flow through URL routing (`app/urls.py` → `app/views/`) to view handlers which dispatch to service layers. Core workflows use LangGraph agents (`app/services/agent/`) to orchestrate multi-step tasks: the scraping service fetches YouTube transcripts, the vector database service stores embeddings, and the reranker improves search quality. When users query a channel or request content generation (notes, mindmaps), the agent coordinates across these services. Structlog handles all observability, with output to both console and JSON files in the `logs/` directory. Settings pull environment variables for API keys (Groq LLM), database config (PostgreSQL or SQLite), and model selection.

## How to run it

### Prerequisites
- Python 3.13.2+
- pip (or poetry/uv)
- Environment variables: `DJANGO_SECRET_KEY`, `DEBUG`, `GROQ_API_KEY` (or your LLM provider key), and optional PostgreSQL credentials

### Setup and run

```bash
# Clone and install dependencies
git clone https://github.com/Umeshwar-Dev/YT-IR.git
cd YT-IR
pip install -e .

# Create environment file
echo "DJANGO_SECRET_KEY=your-secret-key-here" > .env
echo "DEBUG=True" >> .env
echo "GROQ_API_KEY=your-groq-key-here" >> .env

# Run database migrations
python manage.py migrate

# Start development server
python manage.py runserver

# Or production with Gunicorn
gunicorn yt_navigator.wsgi:application --bind 0.0.0.0:8000

pytest tests/
Server will be available at http://localhost:8000.
