FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY app ./app

EXPOSE 8080

CMD ["sh", "-c", "python -m uvicorn app.fast_api_app:app --host 0.0.0.0 --port ${PORT:-8080}"]
