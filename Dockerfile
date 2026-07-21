# Elite Real Estate AI Publisher (Property Oryx) - headless publishing container.
# The desktop UI is for workstations; this image runs scheduled headless
# publish cycles (main.py --headless) against the Property Oryx Agents API.

FROM python:3.13-slim

WORKDIR /opt/publisher

# Install Python dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Data (SQLite DB, processed images) lives on a volume
ENV PUBLISHER_DATA_DIR=/data
VOLUME ["/data", "/opt/publisher/logs", "/opt/publisher/config"]

# Secrets come from the environment (docker compose env_file / secrets):
#   GEMINI_API_KEY, PROPERTYORYX_API_KEY, PUBLISHER_ENCRYPTION_KEY
CMD ["python", "main.py", "--headless"]
