# Use the official vLLM image
FROM vllm/vllm-openai:latest

# Environment variables for offline operation and optimizations
ENV VLLM_NO_USAGE_STATS=1
ENV DO_NOT_TRACK=1

# Expose port
EXPOSE 8000

# The model will be mounted to /app/model at runtime to prevent large image sizes.
# The entrypoint will just start the OpenAI compatible API server.
CMD ["--model", "/app/model", "--tensor-parallel-size", "3", "--quantization", "awq"]
