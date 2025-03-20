   # https://www.youtube.com/watch?v=ikKGMp4jb_o&list=PLlWXhlUMyooawilqK4lPXRvxtbYiw34S8&index=3

import socket
import selectors

selector = selectors.DefaultSelector()


def server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('localhost', 5000))
    server_socket.listen()
    selector.register(fileobj=server_socket, events=selectors.EVENT_READ, data=accept_connection)


def accept_connection(server_socket):
    print('Accept new connection')
    client_socket, adr = server_socket.accept()
    print(f' --> accept for client_socket {client_socket}, {adr}')
    selector.register(fileobj=client_socket, events=selectors.EVENT_READ, data=send_message)



def send_message(client_socket):
    print('    --> socket.recv')
    request = client_socket.recv(256)
    print(f'        recived <{request}>')

    if request:
        response = 'hi'
        print(f'        --> send response = <{response}>')
        client_socket.send(f'{response}\n'.encode())
    else:
        print(f'Break, client_socket {client_socket} closed')
        selector.unregister(client_socket)
        client_socket.close()


def event_loop():
    while True:
        events = selector.select()

        for key, _ in events:
            key.data(key.fileobj)


if __name__ == "__main__":
    server()
    event_loop()
