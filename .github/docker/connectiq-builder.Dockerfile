FROM eclipse-temurin:17-jdk-jammy

ARG SDK_VERSION=unknown
LABEL org.opencontainers.image.description="Connect IQ SDK ${SDK_VERSION} builder/tester"
LABEL org.opencontainers.image.source="https://github.com/ssalonen/garmin-router-widget"

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    libgl1 \
    libgtk-3-0 \
    libsecret-1-0 \
    libusb-1.0-0 \
    libudev1 \
    xdotool \
    imagemagick \
    openssl \
    && rm -rf /var/lib/apt/lists/*

COPY sdk/ /opt/connectiq-sdk/
COPY tester.sh /usr/local/bin/tester.sh

ENV PATH="/opt/connectiq-sdk/bin:${PATH}"

# Device profiles must live at the path the SDK tools expect.
RUN mkdir -p /root/.Garmin/ConnectIQ/Devices
COPY devices/ /root/.Garmin/ConnectIQ/Devices/

RUN chmod +x /opt/connectiq-sdk/bin/* /usr/local/bin/tester.sh

WORKDIR /app
ENTRYPOINT ["tester.sh"]
