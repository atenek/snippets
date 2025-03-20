import socket
from select import select

monitoting_list = []

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(('localhost', 5000))
server_socket.listen()


def accept_connection(server_socket):
    print('Accept new connection')
    client_socket, adr = server_socket.accept()
    print(f' --> accept for client_socket {client_socket}, {adr}')
    monitoting_list.append(client_socket)


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
        monitoting_list.remove(client_socket)
        client_socket.close()


def event_loop():
    while True:
        ready_to_read, _, _ = select(monitoting_list, [], [])

        for sock in ready_to_read:
            if sock is server_socket:
                accept_connection(sock)
            else:
                send_message(sock)


if __name__ == "__main__":
    monitoting_list.append(server_socket)
    event_loop()
