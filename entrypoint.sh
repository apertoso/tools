#!/bin/bash
set -ex


if [ "x$DOCKER_CONF" != "x" ] ; then
    mkdir $HOME/.docker
    echo $DOCKER_CONF > $HOME/.docker/config.json
fi

exec "$@"
