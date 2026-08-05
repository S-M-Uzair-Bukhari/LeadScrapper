FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RUNNING_IN_CONTAINER=1 \
    CHROME_BINARY=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/opt/undetected_chromedriver \
    DISPLAY=:99

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        chromium \
        chromium-driver \
        fonts-liberation \
        tini \
        xauth \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade setuptools \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY upwork_scraper ./upwork_scraper

RUN cp /usr/bin/chromedriver /opt/undetected_chromedriver \
    && mkdir -p /app/data /app/output \
    && useradd --create-home --uid 10001 scraper \
    && chown -R scraper:scraper \
        /app /home/scraper /opt/undetected_chromedriver

USER scraper

VOLUME ["/app/data", "/app/output"]

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/bin/xvfb-run", "-a", "python", "main.py"]
CMD ["--runs", "1"]
