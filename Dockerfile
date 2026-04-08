FROM python:3.11-slim

WORKDIR /app

# Install dependencies as root
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files and set ownership to UID 1000 in one atomic step
COPY --chown=1000:1000 . .

# Switch to the non-root user required by Hugging Face
USER 1000

EXPOSE 7860

# Start the application using the structured entry point
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]