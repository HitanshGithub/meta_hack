FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project files
COPY . .

# Set permissions for the standard Hugging Face user (UID 1000)
RUN chown -R 1000:1000 /app
USER 1000

EXPOSE 7860

# Use the structured server entry point
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]