# Stage 1: Build dependencies and create a virtual environment
FROM python:3.12-alpine AS builder

# Install system dependencies required for building Python packages (like cryptography, cffi)
RUN apk add --no-cache \
    build-base \
    libffi-dev \
    openssl-dev \
    rust \
    cargo

WORKDIR /app

# Create a virtual environment
RUN python -m venv /opt/venv
# Enable venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies into the virtual environment
COPY requirements.txt .
# Use --no-cache-dir to avoid storing downloaded packages
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Production runner (Lightweight)
FROM python:3.12-alpine

# Install only the runtime dependencies needed for C-extensions (like cryptography)
RUN apk add --no-cache libffi openssl

WORKDIR /app

# Copy the pre-built virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Enable venv in the runner
ENV PATH="/opt/venv/bin:$PATH"

# Copy the application code
COPY . .

# Create a non-root user for security best practices
RUN adduser -D appuser && chown -R appuser /app
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Run the application using Uvicorn
CMD ["uvicorn", "asgi:app", "--host", "0.0.0.0", "--port", "8000"]
