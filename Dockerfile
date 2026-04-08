FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Install system dependencies if needed
# RUN apt-get update && apt-get install -y ... && rm -rf /var/lib/apt/lists/*

# Create a non-privileged user (Hugging Face default is often UID 1000)
RUN useradd -m -u 1000 user
USER user
WORKDIR $HOME/app

# Copy and install requirements first for better caching
COPY --chown=user requirements.txt $HOME/app/requirements.txt
RUN pip install --no-cache-dir --user -r $HOME/app/requirements.txt

# Copy the rest of the application
COPY --chown=user . $HOME/app

# Expose the default Hugging Face port
EXPOSE 7860

# Run the application
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]