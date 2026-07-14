FROM python:3.11-slim

WORKDIR /app

# Create a non-root system user to run the process
RUN addgroup --system app && adduser --system --group app

# Install Python dependencies before copying application code
# (layer cache: deps change less often than code)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Drop to non-root
USER app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
