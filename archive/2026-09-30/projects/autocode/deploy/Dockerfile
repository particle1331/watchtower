FROM python:3.14-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .[service]
EXPOSE 8000
CMD ["uvicorn", "autocode_service.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
