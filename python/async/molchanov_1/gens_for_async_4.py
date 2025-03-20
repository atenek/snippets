import socket
from select import select


tasks = []

to_rd = dict()
to_wr = dict()


def server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('localhost', 5000))
    server_socket.listen()

    while True:
        print('Before accept()')
        yield 'r', server_socket
        client_socket, adr = server_socket.accept()
        tasks.append(client(client_socket))
        print(f' --> {client_socket}, {adr}')


def client(client_socket):
    while True:
        yield 'r', client_socket
        request = client_socket.recv(256)

        print(f'   --> request = <{request}>')
        if not request:
            break
        else:
            response = 'Hello world'
            print(f'   --> response = <{response}>')
            yield 'w', client_socket
            client_socket.send(f'{response}\n'.encode())
    client_socket.close()


def event_loop():
    while any([tasks, to_rd, to_wr]):

        while not tasks:
            ready_to_rd, ready_to_wr, _ = select(to_rd, to_wr, [])

            for sock in ready_to_rd:
                tasks.append(to_rd.pop(sock))
            for sock in ready_to_wr:
                tasks.append(to_wr.pop(sock))
        try:
            task = tasks.pop(0)
            reason, sock = next(task)

            if reason == "r":
                to_rd[sock] = task
            if reason == "w":
                to_wr[sock] = task

        except StopIteration:
            print("Done!")


tasks.append(server())
event_loop()
