FROM python:3.11-slim

WORKDIR /app

# Install serving dependencies only (lighter image for the Space).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Create a real non-root user so Python/getpass works on HF Spaces.
RUN useradd -m -u 1000 appuser

# Copy all project files and set ownership to UID 1000 in one atomic step.
COPY --chown=1000:1000 . .

# Switch to the non-root user required by Hugging Face.
USER appuser

ENV HOME=/home/appuser

EXPOSE 7860

# Start the OpenEnv-compatible PR Review server on port 7860.
CMD ["python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]