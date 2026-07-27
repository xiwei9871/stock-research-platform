FROM nginx:1.27-alpine

COPY dashboard/dist /usr/share/nginx/html
COPY deploy/dashboard-nginx.conf /etc/nginx/conf.d/default.conf
