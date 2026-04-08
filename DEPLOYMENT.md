# Deployment Guide

## Quick Start (5 Minutes)

```bash
# Clone and build
git clone <repository-url>
cd pr-review-env
docker build -t pr-review-env .
docker run --rm -p 7860:7860 pr-review-env

# Verify deployment
curl http://localhost:7860/health
python inference.py
```

---

## Docker Deployment

### Build Configuration
```dockerfile
FROM python:3.11-slim

# Security and optimization
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Multi-stage build for efficiency
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Security: non-root user
RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
```

### Production Deployment
```bash
# Build with optimization
docker build -t pr-review-env:latest .

# Run with production settings
docker run -d \
  --name pr-review-env \
  --restart unless-stopped \
  -p 7860:7860 \
  --memory=512m \
  --cpus=1.0 \
  pr-review-env:latest

# Health check
docker exec pr-review-env curl http://localhost:7860/health
```

---

## Hugging Face Spaces Deployment

### Step 1: Create Space
1. Go to [Hugging Face Spaces](https://huggingface.co/spaces)
2. Click "Create new Space"
3. Choose **SDK: Docker**
4. Set Space name (e.g., `pr-review-env`)
5. Make it **Public** or **Private** as needed

### Step 2: Configure Secrets
In Space settings, add secrets:
- `HF_TOKEN`: Your Hugging Face API token

### Step 3: Deploy Code
```bash
git remote add space https://huggingface.co/spaces/<username>/pr-review-env
git push space main
```

### Step 4: Verify Deployment
1. Open your Space URL
2. Check `/health` endpoint
3. Test with `inference.py` locally:
```bash
export ENV_BASE_URL=https://<username>-pr-review-env.hf.space
export HF_TOKEN=your_token
python inference.py
```

---

## Cloud Deployment Options

### AWS ECS (Elastic Container Service)

#### Task Definition
```json
{
  "family": "pr-review-env",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::account:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "pr-review-env",
      "image": "your-account.dkr.ecr.region.amazonaws.com/pr-review-env:latest",
      "portMappings": [
        {
          "containerPort": 7860,
          "protocol": "tcp"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/pr-review-env",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

#### Deployment Commands
```bash
# Build and push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com
docker build -t pr-review-env .
docker tag pr-review-env:latest <account>.dkr.ecr.us-east-1.amazonaws.com/pr-review-env:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/pr-review-env:latest

# Create and run service
aws ecs create-service --cluster pr-review-cluster --service-name pr-review-env --task-definition pr-review-env --desired-count 1
```

### Google Cloud Run

#### Deployment
```bash
# Build and tag
gcloud builds submit --tag gcr.io/PROJECT-ID/pr-review-env

# Deploy to Cloud Run
gcloud run deploy pr-review-env \
  --image gcr.io/PROJECT-ID/pr-review-env \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1
```

### Azure Container Instances

#### Deployment
```bash
# Create resource group
az group create --name pr-review-env-rg --location eastus

# Deploy container
az container create \
  --resource-group pr-review-env-rg \
  --name pr-review-env \
  --image your-registry/pr-review-env:latest \
  --dns-name-label pr-review-env-unique \
  --ports 7860 \
  --cpu 1 \
  --memory 1.5
```

---

## Kubernetes Deployment

### Namespace and ConfigMap
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: pr-review-env
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: pr-review-env-config
  namespace: pr-review-env
data:
  API_BASE_URL: "https://router.huggingface.co/v1"
  MODEL_NAME: "Qwen/Qwen2.5-72B-Instruct"
```

### Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pr-review-env
  namespace: pr-review-env
spec:
  replicas: 2
  selector:
    matchLabels:
      app: pr-review-env
  template:
    metadata:
      labels:
        app: pr-review-env
    spec:
      containers:
      - name: pr-review-env
        image: your-registry/pr-review-env:latest
        ports:
        - containerPort: 7860
        envFrom:
        - configMapRef:
            name: pr-review-env-config
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 7860
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 7860
          initialDelaySeconds: 5
          periodSeconds: 5
```

### Service
```yaml
apiVersion: v1
kind: Service
metadata:
  name: pr-review-env-service
  namespace: pr-review-env
spec:
  selector:
    app: pr-review-env
  ports:
  - protocol: TCP
    port: 80
    targetPort: 7860
  type: LoadBalancer
```

---

## Environment Configuration

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `API_BASE_URL` | `https://router.huggingface.co/v1` | LLM API endpoint |
| `MODEL_NAME` | `Qwen/Qwen2.5-72B-Instruct` | Model to use |
| `HF_TOKEN` | Required | Hugging Face token |
| `ENV_BASE_URL` | `http://127.0.0.1:7860` | Environment URL |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

### Docker Compose
```yaml
version: '3.8'
services:
  pr-review-env:
    build: .
    ports:
      - "7860:7860"
    environment:
      - API_BASE_URL=https://router.huggingface.co/v1
      - MODEL_NAME=Qwen/Qwen2.5-72B-Instruct
      - HF_TOKEN=${HF_TOKEN}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:7860/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## Monitoring and Logging

### Health Checks
```bash
# Basic health
curl http://localhost:7860/health

# Detailed metrics
curl http://localhost:7860/metrics

# System status
curl http://localhost:7860/tasks
```

### Log Monitoring
```bash
# Docker logs
docker logs pr-review-env -f

# Kubernetes logs
kubectl logs -f deployment/pr-review-env -n pr-review-env

# Structured logging example
{"timestamp": "2024-01-01T12:00:00", "level": "INFO", "message": "Step completed", "session_id": "uuid", "reward": 0.95}
```

### Prometheus Metrics (Optional)
```python
# Add to app.py for production monitoring
from prometheus_client import Counter, Histogram, generate_latest

REQUEST_COUNT = Counter('requests_total', 'Total requests', ['method', 'endpoint'])
REQUEST_LATENCY = Histogram('request_duration_seconds', 'Request latency')

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path).inc()
    response = await call_next(request)
    REQUEST_LATENCY.observe(time.time() - start_time)
    return response

@app.get("/metrics")
async def prometheus_metrics():
    return Response(generate_latest(), media_type="text/plain")
```

---

## Security Considerations

### Container Security
- **Non-root user**: Runs as `appuser` with UID 10001
- **Minimal base image**: `python:3.11-slim`
- **No secrets in code**: All sensitive data via environment variables
- **Read-only filesystem**: Where possible

### Network Security
- **HTTPS only**: Use TLS in production
- **Rate limiting**: Consider API gateway
- **Firewall rules**: Restrict access as needed
- **VPC isolation**: Network segmentation

### Operational Security
- **Regular updates**: Keep dependencies current
- **Vulnerability scanning**: Regular security scans
- **Access control**: Proper IAM policies
- **Audit logging**: Track all access

---

## Performance Optimization

### Resource Requirements
- **CPU**: 1 core sufficient for typical load
- **Memory**: 512MB baseline, scales with sessions
- **Storage**: Minimal, <100MB container
- **Network**: Low bandwidth, mostly JSON

### Scaling Strategies
- **Horizontal scaling**: Multiple instances behind load balancer
- **Session affinity**: Not required (stateless per session)
- **Caching**: Consider Redis for session storage
- **CDN**: For static content if needed

### Performance Tuning
```bash
# Optimize Docker build
docker build --no-cache -t pr-review-env .

# Resource limits
docker run --memory=512m --cpus=1.0 pr-review-env

# Performance monitoring
docker stats pr-review-env
```

---

## Troubleshooting

### Common Issues

#### Container Won't Start
```bash
# Check logs
docker logs pr-review-env

# Common fixes
# 1. Check port conflicts
netstat -tulpn | grep 7860

# 2. Verify image build
docker images | grep pr-review-env

# 3. Test locally
python -c "from app import app; print('Import successful')"
```

#### Health Check Fails
```bash
# Manual health check
curl -v http://localhost:7860/health

# Check if service is running
ps aux | grep uvicorn

# Verify port binding
lsof -i :7860
```

#### Inference Connection Issues
```bash
# Test environment connectivity
curl http://localhost:7860/health

# Check environment variables
env | grep ENV_BASE_URL

# Test with correct URL
export ENV_BASE_URL=http://127.0.0.1:7860
python inference.py
```

#### Performance Issues
```bash
# Monitor resource usage
docker stats pr-review-env

# Check for memory leaks
docker exec pr-review-env ps aux

# Profile if needed
python -m cProfile -o profile.stats inference.py
```

### Debug Mode
```bash
# Run with debug logging
docker run -e LOG_LEVEL=DEBUG -p 7860:7860 pr-review-env

# Or locally
uvicorn app:app --reload --log-level debug
```

---

## Backup and Recovery

### Data Backup
- **Configuration**: Git repository
- **Environment variables**: Secure storage
- **Docker images**: Registry backup
- **Monitoring data**: Logs retention

### Disaster Recovery
```bash
# Quick redeployment
docker pull your-registry/pr-review-env:latest
docker run -d --name pr-review-env -p 7860:7860 your-registry/pr-review-env:latest

# Health verification
curl http://localhost:7860/health
python inference.py
```

### Maintenance
```bash
# Update deployment
docker pull your-registry/pr-review-env:latest
docker stop pr-review-env
docker rm pr-review-env
docker run -d --name pr-review-env -p 7860:7860 your-registry/pr-review-env:latest

# Rolling update (Kubernetes)
kubectl set image deployment/pr-review-env pr-review-env=your-registry/pr-review-env:latest
```

This deployment guide ensures production-ready deployment across multiple platforms while maintaining security and operational excellence.
