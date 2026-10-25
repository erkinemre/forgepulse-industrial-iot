"""Actual MQTT broker/subscriber integration, independent of HTTP test client."""
import asyncio
import json
import socket
import threading
import time
import uuid
from datetime import datetime,timezone
from amqtt.broker import Broker
import paho.mqtt.client as mqtt
from shared.model import Measurement
from server.db import Store
from server.collectors import mqtt_loop


def test_mqtt_broker_to_database(tmp_path):
    with socket.socket() as s:
        s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
    ready=threading.Event()
    stop=threading.Event()
    def broker_thread():
        async def run():
            broker=Broker({'listeners':{'default':{'type':'tcp','bind':f'127.0.0.1:{port}'}},
                           'plugins':{'amqtt.plugins.authentication.AnonymousAuthPlugin':{'allow_anonymous':True}}})
            await broker.start(); ready.set()
            while not stop.is_set(): await asyncio.sleep(0.1)
            await broker.shutdown()
        asyncio.run(run())
    thread=threading.Thread(target=broker_thread,daemon=True);thread.start()
    assert ready.wait(5)
    store=Store(tmp_path/'mqtt.db')
    with store.connect() as db:
        db.execute("INSERT INTO devices(id,protocol,config) VALUES(?,?,?)",('belt-2','mqtt',json.dumps({'host':'127.0.0.1','port':port,'topic':'factory/belt-2/measurements'})))
    threading.Thread(target=mqtt_loop,args=(store,),daemon=True).start()
    item=Measurement('belt-2',str(uuid.uuid4()),1,datetime.now(timezone.utc).isoformat(),12,50,7,1,1)
    publisher=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    publisher.connect('127.0.0.1',port,10);publisher.loop_start()
    try:
        deadline=time.time()+8
        while time.time()<deadline:
            publisher.publish('factory/belt-2/measurements',json.dumps(item.json()),qos=1).wait_for_publish(timeout=1)
            with store.connect() as db:
                count=db.execute("SELECT COUNT(*) FROM measurements WHERE event_id=?",(item.event_id,)).fetchone()[0]
            if count: break
            time.sleep(0.3)
        assert count==1
        with store.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM measurements WHERE event_id=?",(item.event_id,)).fetchone()[0]==1
    finally:
        publisher.loop_stop(); publisher.disconnect(); stop.set(); thread.join(timeout=3)
