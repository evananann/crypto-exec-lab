# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --chmod=0444 deploy/continuous-capture/requirements.txt /app/requirements.txt
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    python -m pip install --require-hashes --no-cache-dir -r /app/requirements.txt
RUN groupadd --gid 10001 capture && useradd --uid 10001 --gid capture --no-create-home capture \
    && mkdir /spool /app/research && chmod 0755 /app/research && chown capture:capture /spool
COPY --chmod=0444 research/continuous_capture.py research/clock_telemetry.py /app/research/
COPY --chmod=0444 deploy/continuous-capture/feeds.example.json /app/feeds.json
USER 10001:10001
ENTRYPOINT ["python", "-m", "research.continuous_capture"]
CMD ["capture", "--config", "/app/feeds.json", "--spool", "/spool"]
