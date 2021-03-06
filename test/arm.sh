#!/bin/bash

CLIENT_ID=panel1
REQ_ID=$(dd if=/dev/urandom bs=512 count=12 2>/dev/null | md5sum | awk '{print $1}')
CODE=1234
CA=/etc/mosquitto/ca_certificates/cacert.pem
CERT=/etc/mosquitto/certs/panel1.crt
KEY=/etc/mosquitto/certs/panel1.key
TOPIC=myhome/paradox/requests/${CLIENT_ID}/arming

cat << EOF | mosquitto_pub -d --insecure --cafile ${CA} --cert ${CERT} --key ${KEY} -t ${TOPIC} -s
{
    "clientid": "${CLIENT_ID}",
    "reqid": "${REQ_ID}",
    "request": [
        {
            "type": "arm",
            "code": "${CODE}",
            "arm": [
                {
                    "area": ${1:-1},
                    "arm_type": "regular"
                }
            ]
        }
    ]
}
EOF
