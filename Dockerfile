FROM python:3.12.5-alpine3.20

WORKDIR /src
ENV PYTHONPATH /src

COPY requirements.txt ./
RUN set -e; \
	apk add --no-cache --virtual .build-deps git; \
	pip install -r requirements.txt; \
	apk del .build-deps;

COPY src/announceman announceman/

CMD ["python", "-u", "announceman/main.py"]
