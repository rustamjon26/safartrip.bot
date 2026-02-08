FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"],

CMD ["bash", "-lc", "echo BOT_TOKEN_LEN=${#BOT_TOKEN}; echo ADMINS=$ADMINS; env | grep -E '^(BOT_TOKEN|ADMINS|API_ID|API_HASH)=' || true; python main.py"]
