FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/media \
    && chown -R appuser:appuser /app/media

USER appuser

EXPOSE 10000

CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn x.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 1 --timeout 120"]
