FROM python:3.12-slim
WORKDIR /app

COPY libs ./libs

COPY services/auth-service/requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

COPY services/auth-service/app ./app

ENV PYTHONPATH=/app
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]