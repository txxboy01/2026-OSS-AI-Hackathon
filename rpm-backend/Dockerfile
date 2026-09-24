FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
RUN useradd --create-home --uid 10001 rpm
COPY --chown=rpm:rpm app ./app
COPY --chown=rpm:rpm docs/openapi-v1.yaml ./docs/openapi-v1.yaml
USER rpm
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"
CMD ["python", "-m", "app", "--host", "0.0.0.0"]
