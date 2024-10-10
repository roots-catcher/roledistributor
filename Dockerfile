# Используем официальный образ Python версии 3.9
FROM python:3.9-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файлы проекта в контейнер
COPY requirements.txt /app/
COPY roledistributor.py /app/

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt
RUN touch /app/db/roles.db

# Указываем команду запуска бота
CMD ["python", "roledistributor.py"]
