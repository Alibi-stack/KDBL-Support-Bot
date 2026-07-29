FROM python:3.13-slim

WORKDIR /app

# build-essential -- на случай, если для платформы контейнера (например,
# ARM64 в Parallels на Ubuntu) для каких-то зависимостей sentence-transformers
# нет готового wheel и pip собирает их из исходников.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "main.py"]
