FROM ubuntu:16.04
MAINTAINER prozlach@mesosphere.io

ENV OPENRESTY_VERSION 1.9.15.1
ENV OPENRESTY_DOWNLOAD_URL https://openresty.org/download/openresty-$OPENRESTY_VERSION.tar.gz
ENV OPENRESTY_DOWNLOAD_SHASUM 491a84d70ed10b79abb9d1a7496ee57a9244350b

ENV VENV_DIR /usr/local/venv
ENV AR_CONF_DIR /usr/local/src/adminrouter
ENV OPENRESTY_DIR /usr/local/src/openresty
ENV AR_BIN_DIR /usr/local/adminrouter

WORKDIR /usr/local/src/

# Some remarks when it comes to apt-get udpate:
# * `apt-get update` and `apt-get install` are unreliable. Because of that there
#   is some basic retrying logic
# * we put it on top of every apt-get install, because docker layer cache will
#   not re-run it when updating image with `make update-devkit` if it is a
#   separate `RUN` line. This leads to `404 Not Found errors.

#### Stuff usefull while debugging docker container, not strictly needed for
#### building:
RUN set -ex \
    && bash -x -c 'for i in {1..5}; do apt-get update && break || sleep 2; done' \
    && apt-get install -y --no-install-recommends \
        apt-file \
        dnsutils \
        git \
        iproute2 \
        less \
        psmisc \
        strace \
        tcpdump \
        telnet \
        tree \
        vim

# AR related:
RUN set -ex \
    && bash -x -c 'for i in {1..5}; do apt-get update && break || sleep 2; done' \
    && apt-get install -y --no-install-recommends \
        dnsmasq \
        gcc \
        libdigest-sha-perl \
        libffi-dev \
        libffi6 \
        libpcre++-dev \
        libssl-dev \
        make \
        python3 \
        python3-dev \
        python3-pip \
        python3-virtualenv

# Upgrading pip/setuptools and making the upgrade actually apply in the
# following filesystem layers works more reliable when using a virtualenv for
# creating the Python environment, especially on overlayfs.
# Refs:
#   https://github.com/docker/docker/issues/12327#issuecomment-188921470
#   https://github.com/docker/docker/issues/12327#issuecomment-187158265
RUN python3 -m pip install --upgrade virtualenv
RUN set -ex \
	&& virtualenv --no-site-packages $VENV_DIR \
    && ${VENV_DIR}/bin/pip install --upgrade setuptools pip

ENV PATH ${VENV_DIR}/bin:$PATH

COPY ./requirements-tests.txt .
RUN pip install -r requirements-tests.txt

# Download Vegeta tool for benchmarking
ENV VEGETA_DOWNLOAD_SHA256 2f0a69d0ae6f0bf268b7f655bd37c0104d5568d5b2bc45bbb2c405266f74e33d
ENV VEGETA_DOWNLOAD_URL https://github.com/tsenart/vegeta/releases/download/v6.1.1/vegeta-v6.1.1-linux-amd64.tar.gz

RUN curl -fsSL "$VEGETA_DOWNLOAD_URL" -o vegeta.tar.gz \
    && echo "$VEGETA_DOWNLOAD_SHA256  vegeta.tar.gz" | sha256sum -c - \
        && tar -C /usr/local/bin -xzf vegeta.tar.gz \
        && rm vegeta.tar.gz

# Compile AR, prepare it for running
# This mimics the settings from dcos-image except for '--with-debug'
RUN set -ex \
    && curl -fsSL "$OPENRESTY_DOWNLOAD_URL" -o openresty.tar.gz \
    && echo "$OPENRESTY_DOWNLOAD_SHASUM  openresty.tar.gz" | shasum -c - \
    && mkdir -pv $OPENRESTY_DIR \
    && tar --strip-components=1 -C $OPENRESTY_DIR -xzf openresty.tar.gz \
    && rm openresty.tar.gz \
    && cd $OPENRESTY_DIR \
    && ./configure \
        "--prefix=$AR_BIN_DIR" \
        --with-ipv6 \
        --with-debug \
        --with-file-aio \
        --with-http_gunzip_module \
        --with-http_gzip_static_module \
        --without-mail_pop3_module \
        --without-mail_imap_module \
        --without-mail_smtp_module \
        --with-http_ssl_module \
        --with-luajit \
    && make \
    && make install \
    && mv -v ${AR_BIN_DIR}/nginx/conf/ ${AR_BIN_DIR}/nginx/conf.orig/ \
    && ln -s ${AR_CONF_DIR} ${AR_BIN_DIR}/nginx/conf

# Some AR variables that mimic DC/OS:
COPY ./iam.jwt-key.pub /usr/local/
COPY ./iam.jwt-key.priv /usr/local/
COPY ./iam.jwt-key.shared-secret /usr/local/
ENV IAM_PUBKEY_FILE_PATH=/usr/local/iam.jwt-key.pub
ENV IAM_PRIVKEY_FILE_PATH=/usr/local/iam.jwt-key.priv
ENV IAM_SHARED_SECRET_FILE_PATH=/usr/local/iam.jwt-key.shared-secret
ENV AUTH_ERROR_PAGE_DIR_PATH=${AR_BIN_DIR}/nginx/conf/errorpages

# Some files that mimic DC/OS:
COPY ./ca.crt /run/dcos/pki/CA/certs/ca.crt
COPY ./adminrouter.crt /run/dcos/pki/tls/certs/adminrouter.crt
COPY ./adminrouter.key /run/dcos/pki/tls/private/adminrouter.key
COPY ./adminrouter-redirect-http-https.conf /opt/mesosphere/etc/adminrouter-redirect-http-https.conf
COPY ./adminrouter-upstreams.conf /opt/mesosphere/etc/adminrouter-upstreams.conf

# The contents of this file differ from the one that is shipped with DC/OS:
# the IP addresses Nginx binds to are limited to only 127.0.0.1 instead of *.
# The reason for it is that some endpoints need to listen on TCP port 80 due
# to the way Nginx is configured.
COPY ./adminrouter-listen-master.conf /opt/mesosphere/etc/adminrouter-listen-master.conf
COPY ./adminrouter-listen-agent.conf /opt/mesosphere/etc/adminrouter-listen-agent.conf

# dnsmasq stuff:
COPY ./dnsmasq.conf /etc/dnsmasq.conf
# In case if Docker someday decides to solve:
# https://github.com/docker/docker/issues/1297
# and container's /etc/resolv.conf becomes visible and not bind-mounted.
RUN echo "nameserver 127.0.0.1" > /etc/resolv.conf
RUN echo "nameserver 8.8.8.8\nnameserver 8.8.4.4\n" > /etc/resolv.conf.dnsmasq
COPY ./hosts.dnsmasq /etc/hosts.dnsmasq

WORKDIR $AR_CONF_DIR

CMD ["/bin/bash"]
