FROM paulianttila/mqtt-framework:1.0.2

ARG DIR=/app
ARG APP=app.py

ARG USER=app
ARG GROUP=app

ENV DIR=${DIR}
ENV APP=${APP}

COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

RUN mkdir -p ${DIR}
WORKDIR ${DIR}
COPY src ${DIR}

RUN addgroup -S ${GROUP} && adduser -S ${USER} -G ${GROUP}

# dialEye specific, dialEye only support python 2.7
ARG DIALEYE=dialEye_v10b.zip
ARG DIALEYE_DOWNLOAD_URL=https://olammi.iki.fi/sw/dialEye/${DIALEYE}

ENV LIBRARY_PATH=/lib:/usr/lib

# This hack is widely applied to avoid python printing issues in docker containers.
# See: https://github.com/Docker-Hub-frolvlad/docker-alpine-python3/pull/13
ENV PYTHONUNBUFFERED=1

ARG APK_PACKAGES=curl wget unzip python2 python2-dev py2-setuptools py-pip build-base jpeg-dev zlib-dev

RUN apk add --no-cache ${APK_PACKAGES} \
      && python2 -m ensurepip --upgrade \
      && python2 -m pip install Pillow \
      && apk del build-base \
      && wget -O ${DIALEYE} ${DIALEYE_DOWNLOAD_URL} \
      && unzip ${DIALEYE} -d /opt \
      && rm ${DIALEYE}

# end dialEye

VOLUME /data
WORKDIR /data

USER ${USER}
CMD python ${DIR}/${APP}
