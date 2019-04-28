#!/usr/bin/env sh

CONFIG="../config_prt3.json"
TOPIC="myhome/paradox/#"

mosquitto_sub -d --insecure --cafile $(jq -r '.queue.tls.capath' ${CONFIG}) --cert $(jq -r '.queue.tls.cert' ${CONFIG}) --key $(jq -r '.queue.tls.key' ${CONFIG}) -t ${TOPIC}
