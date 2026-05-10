FROM python:3.12-slim-bookworm@sha256:d384a24aebd583543abb00fa47b2a434ec3a96559c6f244cc3cfcbe9e136a798

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501

WORKDIR /app

RUN addgroup --system liquisto && adduser --system --ingroup liquisto liquisto

COPY requirements.lock requirements.lock
RUN python -m pip install --no-cache-dir -r requirements.lock

COPY --chown=liquisto:liquisto . .

USER liquisto
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=5)" || exit 1

CMD ["python", "-m", "streamlit", "run", "ui/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
