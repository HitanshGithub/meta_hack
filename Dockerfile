FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Create a non-privileged user
RUN useradd -m -u 1000 user
USER user
WORKDIR $HOME/app

# Copy configuration first
COPY --chown=user requirements.txt $HOME/app/requirements.txt
COPY --chown=user pyproject.toml $HOME/app/pyproject.toml

# Install dependencies
RUN pip install --no-cache-dir --user -r $HOME/app/requirements.txt

# Explicitly copy required source code folders
COPY --chown=user server/ $HOME/app/server/
COPY --chown=user pr_review_env/ $HOME/app/pr_review_env/
COPY --chown=user fixtures/ $HOME/app/fixtures/
COPY --chown=user openenv.yaml $HOME/app/openenv.yaml

# Expose the default Hugging Face port
EXPOSE 7860

# Run the application
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]