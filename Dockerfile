FROM python:3.13.14-slim-bookworm@sha256:67a1e1f215ccda113cfc024e8639049257e88f273898f595b61476d128d387e8
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock pyproject.toml ./
RUN python -m pip install --require-hashes -r requirements.lock
COPY src ./src
COPY configs ./configs
COPY data ./data
COPY migrations ./migrations
COPY alembic.ini ./
RUN python -m pip install --no-deps --no-build-isolation -e . \
    && useradd --uid 10001 --create-home aftercare
USER aftercare
EXPOSE 8000
CMD ["python", "-m", "aftercare", "serve", "--offline", "--container-network"]
