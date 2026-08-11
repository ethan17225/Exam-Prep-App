# Pin by digest before deploying: `docker buildx imagetools inspect python:3.12-slim`
# then replace the tag with python:3.12-slim@sha256:<digest>. A bare tag floats,
# so two builds of the same commit can differ.
FROM python:3.12-slim

# Unbuffered so tracebacks reach `docker logs` before a crash instead of dying in
# a block buffer; no .pyc since the image is immutable.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# The lock is hashed and fully resolved; --require-hashes refuses anything whose
# artifact does not match, so a compromised or substituted release cannot be
# pulled in. Regenerate with:
#   uv pip compile --generate-hashes --python-platform linux --python-version 3.12 \
#     -o requirements.lock requirements.txt
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY . .

# Only the writable data dirs are owned by the runtime user. The application code
# stays root-owned so an arbitrary-write bug cannot rewrite a .py file and turn
# into persistent RCE.
RUN chmod +x docker-entrypoint.sh \
    && useradd --create-home --uid 10001 app \
    && mkdir -p /app/uploads /app/Docs \
    && chown -R app:app /app/uploads /app/Docs

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status==200 else 1)"

ENTRYPOINT ["./docker-entrypoint.sh"]
