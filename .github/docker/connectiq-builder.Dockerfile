FROM eclipse-temurin:17-jdk-jammy

ARG SDK_VERSION=unknown
LABEL org.opencontainers.image.description="Connect IQ SDK ${SDK_VERSION} builder/tester"
LABEL org.opencontainers.image.source="https://github.com/ssalonen/garmin-router-widget"

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    libgl1 \
    libgtk-3-0 \
    openssl \
    && rm -rf /var/lib/apt/lists/*

COPY sdk/ /opt/connectiq-sdk/
COPY devices/ /opt/connectiq-sdk/devices/
COPY tester.sh /usr/local/bin/tester.sh

ENV CONNECTIQ_HOME=/opt/connectiq-sdk
ENV PATH="/opt/connectiq-sdk/bin:${PATH}"

RUN chmod +x /opt/connectiq-sdk/bin/* /usr/local/bin/tester.sh

WORKDIR /app
ENTRYPOINT ["tester.sh"]
