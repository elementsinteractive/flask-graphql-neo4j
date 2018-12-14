FROM python:3.7.1-alpine3.8

RUN apk update && apk add build-base \
                      gcc

COPY . /app/

WORKDIR /app/

RUN pip install pipenv
RUN pipenv install --system

CMD echo "Waiting for $NEO4J_HOST:$NEO4J_PORT..." && \
    /app/wait-for.sh $NEO4J_HOST:$NEO4J_PORT && \
    python run.py
