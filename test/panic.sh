#!/bin/bash

set -e

CLIENT_ID=panel1
REQ_ID=$(dd if=/dev/urandom bs=512 count=12 2>/dev/null | md5sum | awk '{print $1}')
CA=/etc/mosquitto/ca_certificates/cacert.pem
CERT=/etc/mosquitto/certs/panel1.crt
KEY=/etc/mosquitto/certs/panel1.key
TOPIC=myhome/paradox/requests/${CLIENT_ID}/panic
PANIC_TYPE=${1:-emergency}

#if [ -z "$1" ]; then
#    PANIC_TYPE=${1}
#fi

cat << EOF | mosquitto_pub -d --insecure --cafile ${CA} --cert ${CERT} --key ${KEY} -t ${TOPIC} -s
{
    "clientid": "${CLIENT_ID}",
    "reqid": "${REQ_ID}",
    "request": [
        {
            "type": "${PANIC_TYPE}",
            "area": 1
        }
    ]
}
EOF
