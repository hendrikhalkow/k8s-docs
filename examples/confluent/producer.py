#!/usr/bin/env python

from confluent_kafka import Producer
producer = Producer(
    {'bootstrap.servers': 'confluent-cp-kafka.yournamespace.svc.cluster.local'}
)

def delivery_report(err, msg):
    """ Called once for each message produced to indicate delivery result.
        Triggered by poll() or flush(). """
    if err is not None:
        print('Message delivery failed: {}'.format(err))
    else:
        print('Message delivered to {} [{}]'.format(msg.topic(), msg.partition()))

for i in range(10):
    data = 'message %d' % i

    # Trigger any available delivery report callbacks from previous produce() calls
    producer.poll(0)

    # Asynchronously produce a message, the delivery report callback
    # will be triggered from poll() above, or flush() below, when the message has
    # been successfully delivered or failed permanently.
    producer.produce('mytopic', data.encode('utf-8'), callback=delivery_report)

# Wait for any outstanding messages to be delivered and delivery report
# callbacks to be triggered.
producer.flush()
