FROM python:3.12-slim
WORKDIR /app
COPY relay.py .
USER 65534:65534
EXPOSE 12346/tcp
CMD ["python", "-u", "relay.py"]
