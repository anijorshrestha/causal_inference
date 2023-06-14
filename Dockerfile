# Dockerfile

# The first instruction is what image we want to base our container on
# We Use an official Python runtime as a parent image
FROM python:3.9

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /code

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

# runs the production server
CMD ["python3", "manage.py", "runserver", "0.0.0.0:8000"]