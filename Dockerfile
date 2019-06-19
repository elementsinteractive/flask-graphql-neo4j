FROM python:3.7.3-alpine3.9

RUN apk add --no-cache build-base gcc

COPY Pipfile* /tmp/
WORKDIR /tmp/
RUN pip install pipenv
RUN pipenv install --system

COPY . /app/
WORKDIR /app/

# we have to wait even after wait-for.sh
# because neo4j doesn't work when it starts listening to a port
CMD echo "Waiting for $NEO4J_HOST:$NEO4J_PORT..." && \
    /app/wait-for.sh -t 60 $NEO4J_HOST:$NEO4J_PORT && \
    sleep 15 && \
    python run.py
