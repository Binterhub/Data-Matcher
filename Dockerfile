# Railway detects this file at the repository root and builds it with no service settings.
FROM python:3.12-slim

WORKDIR /app

COPY arzt-abgleich/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY arzt-abgleich/ .

ENV PORT=5001
EXPOSE 5001

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5001} --workers 1 --timeout 300 'app:create_app()'"]
