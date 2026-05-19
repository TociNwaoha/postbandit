FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    ffmpeg \
    curl \
    wget \
    patchelf \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN find /usr/local/lib/python3.11/site-packages/ctranslate2 -name "*.so*" -exec patchelf --clear-execstack {} +
RUN find /usr/local/lib/python3.11/site-packages -path "*/ctranslate2.libs/*" -name "*.so*" -exec patchelf --clear-execstack {} +

COPY . .

EXPOSE 8000
