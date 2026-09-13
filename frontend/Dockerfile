FROM node:22-alpine

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json* ./
RUN npm install

# Copy source
COPY . .

EXPOSE 5173

# Run Vite dev server, bound to 0.0.0.0 for Docker networking
CMD ["npx", "vite", "dev", "--host", "0.0.0.0", "--port", "5173"]
