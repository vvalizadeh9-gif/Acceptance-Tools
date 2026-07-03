# Uses the ArvanCloud mirror, same fix as Postgres — direct python:3.12-slim
# from Docker Hub would hit the same 403 block.
FROM docker.arvancloud.ir/library/python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh
EXPOSE 8000
CMD ["./entrypoint.sh"]
