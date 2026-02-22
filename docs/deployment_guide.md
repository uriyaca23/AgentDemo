# Deployment Guide

## Air-gapped Organizational Deployment

This guide explains how to deploy the internal LLM inside an offline environment.

### 1. Model Weights Preparation
Download the `Qwen/Qwen2.5-VL-72B-Instruct-AWQ` repository and copy it to the target offline server. 
For example, to `/path/to/weights/Qwen2.5-VL-72B-Instruct-AWQ`.

### 2. Docker Compose
Use the provided `docker/docker-compose.yml`. Update the volume path to match where you stored the model weights:

```yaml
    volumes:
      - /your/actual/path:/app/model
```

Run the container:
```bash
docker-compose up -d
```

### 3. OpenShift Deployment
For OpenShift or Kubernetes clusters, use `docker/openshift-deployment.yaml`.
Ensure the nodes have the NVIDIA device plugin installed. 

Deploy:
```bash
oc apply -f docker/openshift-deployment.yaml
```

The service will be accessible inside the cluster at `http://internal-llm-service:8000`.
