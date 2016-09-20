import argparse
import subprocess
import time
import zmq

def start_fitter(
    nr_fitters=4,
    input_socket='tcp://localhost:7000',
    output_socket='tcp://localhost:8000',
):
    """ Starts a number of fitters to process fitting tasks """
    # Standard input arguments
    input_args = [
        './fitter',
        '--input',  input_socket,
        '--output', output_socket
    ]

    # Start the given number of fitter subprocesses
    return [subprocess.Popen(input_args) for i in range(nr_fitters)]

def run(
  nr_fitters=4,
  task_input_port=7000,
  task_output_port=7001,
  evaluation_input_port=8001,
  evaluation_output_port=8000
):

    fitters = start_fitter(
        nr_fitters=nr_fitters,
        input_socket='tcp://localhost:%d' % task_output_port,
        output_socket='tcp://localhost:%d' % evaluation_input_port
    )
    context = zmq.Context()

    # Listen to requests from "the outside" on ports 7000 and 8000
    puller_request = context.socket(zmq.PULL)
    pusher_request = context.socket(zmq.PUSH)
    puller_request.bind("tcp://*:%d" % task_input_port)
    pusher_request.bind("tcp://*:%d" % task_output_port)

    # The fitter instances are going to connect to the follwing ports
    puller_response = context.socket(zmq.PULL)
    pusher_response = context.socket(zmq.PUSH)
    puller_response.bind("tcp://*:%d" % evaluation_input_port)
    pusher_response.bind("tcp://*:%d" % evaluation_output_port)

    poller = zmq.Poller()
    poller.register(puller_request, zmq.POLLIN)
    poller.register(puller_response, zmq.POLLIN)
    poller.register(pusher_request, zmq.POLLOUT)
    poller.register(pusher_response, zmq.POLLOUT)

    _in = 0
    _out = 0

    tasks = []
    evaluations = []

    while True:

        socks = dict(poller.poll())
        if puller_request in socks and socks[puller_request] == zmq.POLLIN:
            _in += 1
            message = puller_request.recv_string()
            tasks.append(message)

        if pusher_request in socks and socks[pusher_request] == zmq.POLLOUT:
            for task in tasks:
                pusher_request.send_string(task)
            tasks = []

        if puller_response in socks and socks[puller_response] == zmq.POLLIN:
            _out += 1
            message = puller_response.recv_string()
            evaluations.append(message)

        if pusher_response in socks and socks[pusher_response] == zmq.POLLOUT:
            for evaluation in evaluations:
                pusher_response.send_string(evaluation)
            evaluations = []


if __name__ == '__main__':
  parser = argparse.ArgumentParser(
    description='Balances histograms amongst fitter instances'
  )
  parser.add_argument(
    '--nr_fitters', nargs='?', type=int, default=4,
    help='Number of fitter instances to start'
  )
  parser.add_argument(
    '--task_input_port', nargs='?', type=int, default=7000,
    help='Port to listen to for incoming tasks'
  )
  parser.add_argument(
    '--task_output_port', nargs='?', type=int, default=7001,
    help='Port to push tasks for evaluation to'
  )
  parser.add_argument(
    '--evaluation_input_port', nargs='?', type=int, default=8001,
    help='Port to listen to for incoming evaluations'
  )
  parser.add_argument(
    '--evaluation_output_port', nargs='?', type=int, default=8000,
    help='Port to listen to for outgoing evaluation'
  )
  args = parser.parse_args()

  run(
    nr_fitters=args.nr_fitters,
    task_input_port=args.task_input_port,
    task_output_port=args.task_output_port
    evaluation_input_port=args.evaluation_input_port,
    evaluation_output_port=args.evaluation_output_port
  )
