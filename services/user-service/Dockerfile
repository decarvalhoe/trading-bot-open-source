FROM python:3.12-slim
WORKDIR /app

COPY services/user-service/requirements.txt services/user-service/requirements-dev.txt ./
RUN python -m pip install --upgrade pip &&     pip install -r requirements.txt

COPY libs ./libs
COPY services/user-service/app ./app

ENV PYTHONPATH=/app
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]