FROM python:3.11-slim

WORKDIR /app

# Install both serving and training dependencies.
COPY requirements.txt requirements-train.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-train.txt

# Create a real non-root user so Python/getpass and torch caches work.
RUN useradd -m -u 1000 appuser

# Copy all project files and set ownership to UID 1000 in one atomic step.
COPY --chown=1000:1000 . .

# Ensure cache/config dirs are writable at runtime.
RUN mkdir -p /home/appuser/.cache /home/appuser/.config/matplotlib && chown -R 1000:1000 /home/appuser

# Switch to the non-root user required by Hugging Face.
USER appuser

ENV HOME=/home/appuser
ENV XDG_CACHE_HOME=/home/appuser/.cache
ENV MPLCONFIGDIR=/home/appuser/.config/matplotlib
ENV TORCHINDUCTOR_CACHE_DIR=/home/appuser/.cache/torch_inductor

EXPOSE 7860

# For the training Space, boot API + GRPO runner with visible startup diagnostics.
CMD ["sh", "-lc", "echo '[BOOT] training space container started'; ls -l /app/run_training_space.sh; sh /app/run_training_space.sh"]