# This file is part of REANA.
# Copyright (C) 2024 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

# Use Ubuntu LTS base image
FROM docker.io/library/ubuntu:20.04

# Use default answers in installation commands
ENV DEBIAN_FRONTEND=noninteractive

# Use distutils provided by the standard Python library instead of the vendored one in
# setuptools, so that editable installations are stored in the right directory.
# See https://github.com/pypa/setuptools/issues/3301
ENV SETUPTOOLS_USE_DISTUTILS=stdlib

# Add sources to `/code` and work there
WORKDIR /code
COPY . /code

# Install system dependencies and reana-client in one go
# hadolint ignore=DL3008,DL3013
RUN apt-get update -y && \
    apt-get install --no-install-recommends -y \
      gcc \
      libpython3.8 \
      python3-pip \
      python3.8 \
      python3.8-dev && \
    # `pip3 install kubernetes` needed due to an old version of system pip3
    pip3 install --no-cache-dir kubernetes '.[tests]' && \
    apt-get remove -y \
      gcc \
      python3.8-dev && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /code /var/lib/apt/lists/*

# Run container as `reana` user with UID `1000`, which should match
# current host user in most situations
# hadolint ignore=DL3059
RUN adduser --uid 1000  reana --gid 0 && \
    chown -R reana:root /home/reana
WORKDIR /home/reana

# Run reana-client upon entry
USER reana
ENTRYPOINT ["reana-client"]

# Set image labels
LABEL org.opencontainers.image.authors="team@reanahub.io"
LABEL org.opencontainers.image.created="2024-03-14"
LABEL org.opencontainers.image.description="REANA reproducible analysis platform - command-line client"
LABEL org.opencontainers.image.documentation="https://reana-client.readthedocs.io/"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/reanahub/reana-client"
LABEL org.opencontainers.image.title="reana-client"
LABEL org.opencontainers.image.url="https://github.com/reanahub/reana-client"
LABEL org.opencontainers.image.vendor="reanahub"
# x-release-please-start-version
LABEL org.opencontainers.image.version="0.9.3"
# x-release-please-end
