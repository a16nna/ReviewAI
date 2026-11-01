FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends default-jre-headless cppcheck nodejs npm curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN bash tools/setup.sh && useradd -m app && mkdir /data && chown -R app /app /data
USER app
ENV DATABASE_URL=sqlite:////data/reviewai.db
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
