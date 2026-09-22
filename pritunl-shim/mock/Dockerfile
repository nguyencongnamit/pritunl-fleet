# Mock Pritunl OSS node for the test lab.
# Build context must be the pritunl-shim/ directory (see docker-compose.yml)
# so the shared `shim/` package (hmac_auth) is available to the mock.
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.111" "uvicorn[standard]>=0.30"

COPY shim/ /app/shim/
COPY mock/ /app/mock/

ENV PYTHONPATH=/app
EXPOSE 9700

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9700/').status==200 else 1)"

CMD ["uvicorn", "mock.mock_node:app", "--host", "0.0.0.0", "--port", "9700"]
