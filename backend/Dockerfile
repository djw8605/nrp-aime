FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
# amieclient pins python-dateutil<2.7 which is incompatible with Python 3.11
# (collections.Callable was removed). Install it without its deps so pip does
# not enforce that stale constraint; requirements.txt supplies a compatible dateutil.
RUN pip install --no-cache-dir "amieclient>=0.4.0" --no-deps && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8000
