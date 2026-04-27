# Streamlit application image for the Oracle 2PC Simulator.
#
# Uses python:3.11-slim as the base to keep the image small.  No Oracle
# Instant Client is installed; python-oracledb runs in thin mode and
# connects to the Oracle nodes over TCP using the EZConnect DSN format.
#
# The src/ directory is bind-mounted at runtime (see docker-compose.yml)
# so code changes are visible inside the container without a rebuild.
# The COPY src/ step below ensures the image also works as a standalone
# deployment where no volume mount is present.

FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies before copying source code so that Docker
# can cache this layer and avoid a full pip install on every code change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 8501

# Run Streamlit in headless mode so it does not try to open a browser.
# server.address=0.0.0.0 is required for the port mapping in docker-compose
# to reach the application from the host.
CMD ["streamlit", "run", "src/app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true"]
