FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm

# ReportLab requires a Korean TrueType font; Windows fonts are not copied.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-nanum \
    && rm -rf /var/lib/apt/lists/*
