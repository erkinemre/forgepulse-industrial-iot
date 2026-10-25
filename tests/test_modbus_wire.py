"""Real TCP wire check against the simulator's register datastore."""
import socket
import threading
import time
from pymodbus.client import ModbusTcpClient
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext, ModbusDeviceContext
from pymodbus.server import StartTcpServer
from shared.simulator import Belt
from vm.modbus_codec import encode, decode


def test_modbus_tcp_wire():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
    b=Belt(produced=123456, rejected=4, temperature_c=48.25, current_a=7.31, state=1)
    ir,hr=encode(b)
    device=ModbusDeviceContext(ir=ModbusSequentialDataBlock(0,[0]*32),hr=ModbusSequentialDataBlock(0,[0]*8))
    device.setValues(4,0,ir); device.setValues(3,0,hr)
    context=ModbusServerContext(devices={1:device},single=False)
    threading.Thread(target=lambda:StartTcpServer(context=context,address=('127.0.0.1',port)),daemon=True).start()
    client=ModbusTcpClient('127.0.0.1',port=port,timeout=1,retries=0)
    for _ in range(20):
        if client.connect(): break
        time.sleep(0.1)
    assert client.connected
    inputs=client.read_input_registers(0,count=20,device_id=1)
    holding=client.read_holding_registers(0,count=1,device_id=1)
    assert not inputs.isError() and not holding.isError()
    assert decode(inputs.registers,holding.registers)==dict(produced=123456,temperature_c=48.25,current_a=7.31,rejected=4,state=1)
    client.close()
