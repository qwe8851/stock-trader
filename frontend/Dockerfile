# =============================================================================
# Frontend Dockerfile - React + Vite
# Multi-stage build: build stage → production nginx stage
# =============================================================================

# ---- Build stage ----
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency files first for better layer caching
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build the app (outputs to /app/dist)
RUN npm run build


# ---- Production stage ----
FROM nginx:1.27-alpine AS production

# Copy built assets from the build stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx configuration for SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
