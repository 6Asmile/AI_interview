# ai-interview-frontend/Dockerfile
FROM node:18-alpine AS builder
WORKDIR /app
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_WS_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_WS_URL=${VITE_WS_URL}
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build  

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
