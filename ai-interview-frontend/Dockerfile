# ai-interview-frontend/Dockerfile
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build  

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html  