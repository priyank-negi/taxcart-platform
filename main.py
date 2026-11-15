"""Entry point: `uvicorn main:app --host 0.0.0.0 --port $PORT`."""
from portal.app import create_app

app = create_app()
