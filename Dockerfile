FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies
COPY requirements.txt requirements-optional.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-optional.txt

# Copy all project files
COPY . .

# Hugging Face Spaces requires the app to listen on port 7860
EXPOSE 7860

# Startup sequence:
# 1. Create DB schema and users
# 2. Generate and analyze demo data (takes ~1 min, runs every time the Space wakes up)
# 3. Start FastAPI in the background on port 8000
# 4. Start Streamlit in the foreground on port 7860
CMD python -m app.db.migrate && \
    python -m app.simulator.seed_demo && \
    python -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000 & \
    python -m streamlit run app/ui/Home.py --server.port=7860 --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false