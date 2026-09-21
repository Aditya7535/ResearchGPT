# ==============================================================================
# Stage 1: Build React + Vite SPA
# ==============================================================================
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (leverage Docker layer caching)
COPY package*.json ./
RUN npm ci

# Copy application source and compile
COPY . .
RUN npm run build

# ==============================================================================
# Stage 2: Serve with Nginx Alpine
# ==============================================================================
FROM nginx:alpine

# Remove default nginx static files
RUN rm -rf /usr/share/nginx/html/*

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom Nginx configuration with reverse proxy
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
