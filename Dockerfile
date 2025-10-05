# Use the official Python 3.11 slim image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the server script into the container
COPY server.py .

# Install the required Python packages
RUN pip install --no-cache-dir fastmcp beautifulsoup4

# Expose port 8080
EXPOSE 8080

# Command to run the FastMCP server
CMD ["python", "server.py"]
