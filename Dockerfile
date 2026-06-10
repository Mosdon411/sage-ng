# Use official lightweight Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY sage_server.py /app/
COPY sage-ng-dashboard.html /app/
COPY backend/ /app/backend/

# Expose port
EXPOSE 8000

# Run server
CMD ["python", "sage_server.py"]
