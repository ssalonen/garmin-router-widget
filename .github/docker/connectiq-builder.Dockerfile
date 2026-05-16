FROM eclipse-temurin:17-jdk-jammy

ARG SDK_VERSION=unknown
LABEL org.opencontainers.image.description="Connect IQ SDK ${SDK_VERSION} builder/tester"
LABEL org.opencontainers.image.source="https://github.com/ssalonen/garmin-router-widget"

RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository universe \
    && apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    libgl1 \
    libgtk-3-0 \
    libsecret-1-0 \
    libusb-1.0-0 \
    libudev1 \
    libwebkit2gtk-4.0-37 \
    xdotool \
    imagemagick \
    openssl \
    && rm -rf /var/lib/apt/lists/*

COPY sdk/ /opt/connectiq-sdk/
COPY tester.sh /usr/local/bin/tester.sh

ENV PATH="/opt/connectiq-sdk/bin:${PATH}"
ENV CONNECTIQ_HOME=/opt/connectiq-sdk

# Device profiles and font bitmaps must live at the paths the SDK tools
# expect. The simulator looks for Fonts/ at this hardcoded location
# regardless of CONNECTIQ_HOME, which is why fonts were missing.
RUN mkdir -p /root/.Garmin/ConnectIQ/Devices /root/.Garmin/ConnectIQ/Fonts
COPY devices/ /root/.Garmin/ConnectIQ/Devices/
COPY fonts/ /root/.Garmin/ConnectIQ/Fonts/

RUN chmod +x /opt/connectiq-sdk/bin/* /usr/local/bin/tester.sh

# Verify all simulator shared-library dependencies are satisfied.
# This turns a confusing runtime crash into a clear build failure.
RUN echo "=== ldd simulator ===" && ldd /opt/connectiq-sdk/bin/simulator && \
    ! ldd /opt/connectiq-sdk/bin/simulator | grep -q "not found"

WORKDIR /app
ENTRYPOINT ["tester.sh"]
