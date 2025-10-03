#!/bin/bash

export PYTHONPATH=/home/ubuntu/trading-bot-open-source
export DATABASE_URL=postgresql+psycopg2://trading:trading@localhost:5432/trading
export REDIS_URL=redis://localhost:6379/0
export JWT_SECRET=demo-secret-key
export ENVIRONMENT=dev

# Démarrer les services essentiels
echo "Démarrage des services de démonstration..."

# Service d'authentification
cd services/auth_service
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8011 &
AUTH_PID=$!

# Attendre un peu
sleep 3

# Service algo-engine (stratégies)
cd ../algo_engine
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8014 &
ALGO_PID=$!

# Service web dashboard
cd ../web_dashboard
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8022 &
WEB_PID=$!

echo "Services démarrés:"
echo "- Auth Service: http://localhost:8011"
echo "- Algo Engine: http://localhost:8014" 
echo "- Web Dashboard: http://localhost:8022"
echo ""
echo "PIDs: AUTH=$AUTH_PID ALGO=$ALGO_PID WEB=$WEB_PID"
echo "Pour arrêter: kill $AUTH_PID $ALGO_PID $WEB_PID"

wait
