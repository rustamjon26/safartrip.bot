FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Security: Remove any accidentally copied sensitive files
RUN rm -f .env *.db

# Run bot
CMD ["python", "main.py"]
