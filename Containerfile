FROM python:3.10-slim
COPY . /app
WORKDIR /app
RUN pip install .
CMD ["pybt2"]
