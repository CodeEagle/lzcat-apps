FROM python:3.12-slim

ARG UPSTREAM_REF=7f02ee1f87ee9ad1605176d0a42e1c47374834b5
ARG SOURCE_VERSION=unknown
ARG BUILD_VERSION=unknown

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

COPY landing_app.py /app/landing_app.py
COPY landing_page.html /app/landing_page.html

RUN python -m pip install --upgrade pip \
    && python -m pip install "git+https://github.com/CodeEagle/StoryBoatTTSGateway.git@${UPSTREAM_REF}"

LABEL org.opencontainers.image.version="${BUILD_VERSION}"
LABEL org.opencontainers.image.revision="${UPSTREAM_REF}"
LABEL org.opencontainers.image.ref.name="${SOURCE_VERSION}"

EXPOSE 5051

CMD ["python", "-m", "uvicorn", "landing_app:app", "--host", "0.0.0.0", "--port", "5051"]
