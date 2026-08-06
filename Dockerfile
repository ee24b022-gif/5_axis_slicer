FROM python:3.11-slim

# Install g++ and build tools
RUN apt-get update && apt-get install -y g++ make && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt /app/backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY . /app/
RUN cd backend && g++ -std=c++17 -O2 -o slicer_engine slicer.cpp && chmod +x slicer_engine

# Create dummy frontend dist to satisfy FastAPI StaticFiles mount
RUN mkdir -p /app/frontend/dist && echo "<html><body>Frontend is served by Vercel</body></html>" > /app/frontend/dist/index.html

EXPOSE 10000
WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-10000}"]
