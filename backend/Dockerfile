FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
# amieclient comes from djw8605/amieclient@1700828 (upstream PR xsede/amieclient#35):
# fixes Compute ParentRecordID serialization, adds UsageClient.loaded(),
# keeps POSTs under the 256 KB limit, and defaults to usage.access-ci.org. Switch back to PyPI once upstream releases it.
# Installed without deps: its python-dateutil pin is stale; requirements.txt
# supplies requests and a compatible dateutil.
ARG AMIECLIENT_URL=https://github.com/djw8605/amieclient/archive/1700828b80fce7e5c97f690bc1a0f9b4c9ffd001.tar.gz
RUN pip install --no-cache-dir --no-deps "amieclient @ ${AMIECLIENT_URL}" && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8000
