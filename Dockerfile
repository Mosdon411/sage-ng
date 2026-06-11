# Dockerfile - SAGE-NG
FROM python:3.11-slim

WORKDIR /app

# Copy requirements first (for better caching)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application files
COPY sage_server.py /app/
COPY sage-ng-dashboard.html /app/
# Remove or comment out the backend/ line:
# COPY backend/ /app/backend/

# Expose port
EXPOSE 8000

# Run the server
CMD ["uvicorn", "sage_server:app", "--host", "0.0.0.0", "--port", "8000"]
