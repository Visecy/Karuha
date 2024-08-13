FROM python:3.10

WORKDIR /opt/karuha
COPY . .

RUN pip install .[all] -i https://pypi.tuna.tsinghua.edu.cn/simple

CMD [ "python" , "-m" , "karuha" ]
