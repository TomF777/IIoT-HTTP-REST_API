#!bin/bash

sudo docker build --build-arg date=$(date -u +'%Y-%m-%dT%H:%M:%SZ') --tag fastapi_http_server_analytics_img:0.0.1 ../. 
