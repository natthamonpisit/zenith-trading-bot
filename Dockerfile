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
# Direct simple command - no scripts
# Force cache bust for this build
ENV CACHE_BUST=20260126_2
ENV PYTHONUNBUFFERED=1

# Direct simple command - no scripts
# Direct simple command - no scripts
# FIX: Use shell to create config.toml dynamically with the CORRECT PORT then run
CMD sh -c "mkdir -p .streamlit && \
    echo '[server]\nheadless = true\naddress = \"0.0.0.0\"\nport = '\"$PORT\"'\nenableCORS = false\nenableXsrfProtection = false\nfileWatcherType = \"none\"\n\n[browser]\ngatherUsageStats = false' > .streamlit/config.toml && \
    streamlit run dashboard/app.py & \
    sleep 5 && \
    python -u main.py"
