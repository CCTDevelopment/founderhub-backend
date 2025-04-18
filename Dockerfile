FROM python:3.11-slim

WORKDIR /app

# Install WeasyPrint system-level dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libglib2.0-0 \
    libxml2 \
    libxslt1.1 \
    libjpeg-dev \
    libpng-dev \
    libffi-dev \
    libssl-dev \
    curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy everything inside /app folder from host to /app/app in container
COPY app /app/app

# Expose templates and static at the right paths inside container
RUN mkdir -p /app/templates /app/static \
 && cp -r /app/app/templates/* /app/templates/ \
 && cp -r /app/app/static/* /app/static/

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9001"]
