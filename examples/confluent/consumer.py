#!/usr/bin/env python

from confluent_kafka import Consumer, KafkaError

consumer = Consumer({
    'bootstrap.servers': 'confluent-cp-kafka.yournamespace.svc.cluster.local',
    'group.id': 'mygroup',
    'auto.offset.reset': 'earliest'
})

consumer.subscribe(['mytopic'])

while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("Consumer error: {}".format(msg.error()))
        continue
    print('Received message: {}'.format(msg.value().decode('utf-8')))

consumer.close()
