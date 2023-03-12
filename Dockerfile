FROM paulianttila/mqtt-framework:1.1.1

ARG DIR=/app
ARG APP=app.py
ARG WEBDIR=/web

ARG USER=app
ARG GROUP=app

ENV DIR=${DIR}
ENV APP=${APP}

COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

RUN mkdir -p ${WEBDIR}
WORKDIR ${WEBDIR}
COPY web ${WEBDIR}

RUN mkdir -p ${DIR}
WORKDIR ${DIR}
COPY src ${DIR}

RUN addgroup -S ${GROUP} && adduser -S ${USER} -G ${GROUP}

ARG DIALEYE=dialeye.zip
ARG DIALEYE_DOWNLOAD_URL=https://github.com/paulianttila/dialeye-docker/archive/refs/tags/v1.0b.zip
ARG DIALEYE_UNZIP_DIR=dialeye-docker-1.0b

ARG APK_PACKAGES="curl"

RUN apk add --no-cache ${APK_PACKAGES} \
      && wget -O ${DIALEYE} ${DIALEYE_DOWNLOAD_URL} \
      && unzip ${DIALEYE} -d /opt \
      && mv /opt/${DIALEYE_UNZIP_DIR}/dialEye /opt \
      && rm -R /opt/${DIALEYE_UNZIP_DIR} \
      && rm ${DIALEYE}

VOLUME /data
WORKDIR /data

USER ${USER}
CMD python ${DIR}/${APP}
