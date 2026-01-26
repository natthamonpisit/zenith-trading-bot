# Use official Python image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies (for building some python packages)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose port for Streamlit
EXPOSE 8501

# Run both the bot and the dashboard using a simple shell script
# Use $PORT environment variable provided by Railway
# Execute directly to ensure runtime variable expansion
# CRITICAL: Run ONLY Streamlit first with aggressive cloud settings
# Copy and set permissions for entrypoint
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Use shell form to ensure variable checking works if needed, 
# but exec form is better for signal handling. 
# We use ENTRYPOINT to force this script to be the PID 1
ENTRYPOINT ["/app/entrypoint.sh"]
