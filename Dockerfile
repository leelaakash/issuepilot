FROM python:3.11-slim

# System deps — git for cloning, docker CLI for sandboxing
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run the CLI (override CMD to start server)
ENTRYPOINT ["python", "main.py"]
CMD ["--help"]
