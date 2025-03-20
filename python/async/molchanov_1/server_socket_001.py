import socket

""" Server socket example
> nc 127.0.0.1 5000  # bash client
"""

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(('localhost', 5000))
server_socket.listen()

while True:  # outer while
    print('Before accept()')
    client_socket, adr = server_socket.accept()
    print(f' --> {client_socket}, {adr}')

    while True:  # inner while
        request = client_socket.recv(256)
        print(f'   --> request = <{request}>')

        if not request:
            client_socket.close()
            print(f'Break, client_socket {adr} closed')
            break
        else:
            response = 'Hello world'
            print(f'   --> response = <{response}>')
            client_socket.send(f'{response}\n'.encode())

    print("after inner while loop")
    client_socket.close()
