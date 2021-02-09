import os
from queue import Queue
from threading import Lock, Thread
from time import time
import logging
from logging.handlers import TimedRotatingFileHandler

from max30102 import MAX30102
from algorithm import Rf_Algorithm

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(message)s')
logger = logging.getLogger('datareader')
handler = TimedRotatingFileHandler('log/log',when='midnight', backupCount=365)
handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(handler)


class DataReader():
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

    def init(self):
        m = MAX30102()
        m.setup()
        self.sensor = m
        self.STARTED = True

        print("MAX30102 initialized")

    def start(self):
        print("Starting to read data in new thread")
        lock = Lock()
        t = Thread(target=self.serve_data, args=(lock,))
        t.start()
        # t.join()

    def stop(self):
        self.sensor.shutdown()
        self.STARTED = False
        print("Finished")

    def read(self, lock=None):
        if lock:
            lock.acquire()
        red, ir = self.sensor.read_sequential(1)
        self.red = red[0]
        self.ir = ir[0]
        self.red_buf.append(self.red)
        self.ir_buf.append(self.ir)
        self.get_hr_spo2()
        if lock:
            lock.release()
        return self.red, self.ir, self.hr, self.hr_v, self.spo2, self.spo2_v

    def get_values(self):
        return self.red, self.ir, self.hr, self.hr_v, self.spo2, self.spo2_v

    def get_hr_spo2(self, moving_average=True, ma_length=4, exp_ma=False):
        if len(self.ir_buf) == 100 and len(self.ir_buf) == 100:
            hr, hr_v, spo2, spo2_v = self.algo.heart_rate_and_oxygen_saturation(
                self.red_buf, self.ir_buf)
            if hr_v and spo2_v:
                logger.info(f"HR {hr} SpO2 {spo2:.{4}}")
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

    def serve_data(self, lock):
        print("Serving data from thread")
        while True:
            if self.STARTED:
                self.read(lock)
            else:
                break
