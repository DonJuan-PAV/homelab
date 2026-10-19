FROM python:3.12-slim

# Show logs immediately (needed to see the Outlook sign-in code with docker logs)
ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

EXPOSE 8080
CMD ["python", "src/main.py"]
