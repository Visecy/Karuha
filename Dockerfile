FROM python:3.10-slim

LABEL maintainer="ovizro@visecy.org"

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Install pip requirements
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade -r requirements.txt

WORKDIR /opt/karuha
COPY . .

RUN pip install .[all] -i https://pypi.tuna.tsinghua.edu.cn/simple

CMD [ "python" , "-m" , "karuha" ]
