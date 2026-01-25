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
# Note: For production GCP, it's often better to run them as separate services, 
# but for a single container deployment, we can use a wrapper.
RUN echo '#!/bin/bash\n\
    python main.py & \n\
    streamlit run dashboard/app.py --server.port 8080 --server.address 0.0.0.0\n\
    ' > start.sh && chmod +x start.sh

# Streamlit runs on 8501 by default, but Cloud Run expects 8080
ENV PORT=8080

CMD ["./start.sh"]
