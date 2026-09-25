FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput
RUN useradd --create-home --uid 10001 appuser && mkdir -p /app/media && chown -R appuser:appuser /app/media
USER appuser
EXPOSE 8000
CMD ["gunicorn", "x.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
