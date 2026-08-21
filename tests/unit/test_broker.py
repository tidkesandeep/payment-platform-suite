from payment_platform.streaming.broker import BrokerError, InMemoryBroker


def test_in_memory_broker_records_produces():
    broker = InMemoryBroker()
    broker.produce("payments", "cust_1", {"event_id": "e1"})
    assert len(broker.records) == 1
    assert broker.records[0].topic == "payments"


def test_in_memory_broker_raises_when_down():
    broker = InMemoryBroker()
    broker.fail = True
    try:
        broker.produce("payments", "cust_1", {"event_id": "e1"})
    except BrokerError:
        return
    raise AssertionError("expected BrokerError")
