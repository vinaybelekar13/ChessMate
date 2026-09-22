FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
# NOTE: MinerU/Docling/LightRAG have their own, often heavier, install steps
# (some need CUDA-capable images for OCR models). Adjust base image accordingly
# once you've confirmed which of them you're actually running.
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
