#! bin/python
from flask import Flask, render_template, copy_current_request_context
from flask_socketio import SocketIO, emit, disconnect
from threading import Thread, Lock
from time import sleep, time, gmtime

from datareader import DataReader

async_mode = None
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socket_ = SocketIO(app, cors_allowed_origins=[])


@app.route('/')
def index():
    return render_template('old_index.html',
                           sync_mode=socket_.async_mode)


@socket_.on('connect', namespace='/biometrics')
def test_connect():
    emit('connected', {'data': 'Connected'})
    print('Client connected')


@socket_.on('disconnect_request', namespace='/biometrics')
def disconnect_request():
    @copy_current_request_context
    def can_disconnect():
        disconnect()
    print('Client disconnected')
    emit('my_response',
         {'data': 'Disconnected!'}, callback=can_disconnect)


if __name__ == '__main__':

    reader = DataReader()

    def send_data():
        while True:
            red, ir, hr, hr_v, spo2, spo2_v = reader.get_values()
            payload = {'t': round(time()), 'red': red, 'ir': ir, 'hr': hr,
                       'hr_v': hr_v, 'spo2': spo2, 'spo2_v': spo2_v}
            socket_.emit('data', payload, namespace="/biometrics")
            socket_.sleep(0.1)

    reader.init()
    reader.start()

    socket_.start_background_task(target=send_data)
    socket_.run(app, debug=False)
