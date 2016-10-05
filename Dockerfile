FROM ubuntu:xenial

COPY . /opt/tools/

RUN set -x && \
    apt-get update && \
    apt-get install -y python git python-pip python-dev libpq-dev libxml2-dev libxslt1-dev apt-transport-https ca-certificates unzip wget && \
    apt-key adv --keyserver hkp://p80.pool.sks-keyservers.net:80 --recv-keys 58118E89F3A912897C070ADBF76221572C52609D && \
    wget -O- http://apt.apertoso.be/apertosonv.gpg.key | apt-key add - && \
    echo "deb https://apt.dockerproject.org/repo ubuntu-xenial main" > /etc/apt/sources.list.d/docker.list && \
    echo "deb http://apt.apertoso.be/ubuntu xenial main" > /etc/apt/sources.list.d/apertoso.list && \
    apt-get update && apt-cache policy docker-engine && \
    apt-get install -y docker-engine p7zip && \
    pip install -r /opt/tools/requirements.txt && \
    mkdir /root/.ssh && \
    mv /opt/tools/.gitlab-ci-deploy.key /root/.ssh/id_rsa && \
    ssh-keyscan -H gitlab.apertoso.be >> ~/.ssh/known_hosts && \
    ssh-keyscan -H github.com >> ~/.ssh/known_hosts && \
    chmod -R 600 /root/.ssh

ADD ./entrypoint.sh /
ENTRYPOINT ["/entrypoint.sh"]
