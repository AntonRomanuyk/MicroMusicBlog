#!/bin/bash

# Останавливаем скрипт если есть ошибка
set -e

# Запуск FastAPI приложения через uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
