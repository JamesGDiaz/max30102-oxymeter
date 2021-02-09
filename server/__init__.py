from time import time
import math
import numpy as np
import asyncio
import websockets

from max30102 import MAX30102
from algorithm import Rf_Algorithm

class DataServer():
    def __init__(self):
        print("Initializing")
        self.STARTED = False
        self.ir = 0
        self.red = 0
        self.hr = 0
        self.hr_v = False
        self.old_hr = []
        self.spo2 = 0
        self.spo2_v = False
        self.old_spo2 = []
        self.red_buf = []
        self.ir_buf = []
        self.algo = Rf_Algorithm()

    def start(self):
        m = MAX30102()
        m.setup()
        self.sensor = m
        self.STARTED = True

    def stop(self):
        self.sensor.shutdown()
        self.STARTED = False
        print("Finished")

    async def read(self):
        red, ir = self.sensor.read_sequential(1)
        self.red = red[0]
        self.ir = ir[0]
        self.red_buf.append(self.red)
        self.ir_buf.append(self.ir)
        return self.red, self.ir

    def start_websocket(self, port=1933):
        address = "192.168.0.23"
        #address = "localhost"
        if self.STARTED:
            start_server = websockets.serve(
                self.serve_data, address, port)
            print(f"Websocket serving data in ws://{address}:{port}")
            asyncio.get_event_loop().run_until_complete(start_server)
            asyncio.get_event_loop().run_forever()
        else:
            print("Sensor not started. Run DataRecorder.start() first")

    def get_hr_spo2(self, moving_average=True, ma_length=4, exp_ma=False):
        if len(self.ir_buf) == 100 and len(self.ir_buf) == 100:
            hr, hr_v, spo2, spo2_v = self.algo.heart_rate_and_oxygen_saturation(
                self.red_buf, self.ir_buf)

            self.hr_v = hr_v
            if hr_v:
                self.hr = hr
                self.old_hr.append(self.hr)
            self.spo2_v = spo2_v
            if spo2_v:
                self.spo2 = spo2
                self.old_spo2.append(self.spo2)

            # clear buffers
            self.red_buf = []
            self.ir_buf = []

        if moving_average:
            hr_ma = round(sum(self.old_hr[-ma_length:])/ma_length)
            spo2_ma = round(sum(self.old_spo2[-ma_length:])/ma_length)
            return hr_ma, self.hr_v, spo2_ma, self.spo2_v

        return self.hr, self.hr_v, self.spo2, self.spo2_v

    async def serve_data(self, websocket, path):
        print("Serving data")
        tstart = int(round(time() * 1000))
        while True:
            red_led, ir_led = await self.read()
            hr, hr_v, spo2, spo2_v = self.get_hr_spo2()
            tend = int(round(time() * 1000))
            #print(f"{red_led} , {ir_led}")
            #print(hr, hr_valid, spo2, spo2_valid)
            payload = f"{tend-tstart},{red_led},{ir_led},{hr},{hr_v},{spo2},{spo2_v}"
            #print(payload)
            await websocket.send(payload)


# 100 samples are read and used for HR/SpO2 calculation in a single loop
if __name__ == '__main__':
    server = DataServer()

    server.start()
    server.start_websocket()
