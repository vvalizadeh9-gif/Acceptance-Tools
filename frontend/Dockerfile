# Stage 1: build the React app into plain static files
FROM docker.arvancloud.ir/library/node:20-slim AS build
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

# Stage 2: serve those static files with Nginx, which also
# reverse-proxies /api/ to the backend container (see nginx.conf)
FROM docker.arvancloud.ir/library/nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
