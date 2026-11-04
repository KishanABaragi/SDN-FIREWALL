import socket
import threading

LISTEN_HOST = '10.0.0.5'
LISTEN_PORT = 6002
LOGGER_HOST = '10.0.0.4'
LOGGER_PORT = 6000

def handle(conn):
    try:
        with conn:
            data = b''
            while b'\n' not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            if data:
                with socket.create_connection((LOGGER_HOST, LOGGER_PORT), timeout=3) as logger:
                    logger.sendall(data)
    except OSError as exc:
        print('Relay error:', exc, flush=True)

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((LISTEN_HOST, LISTEN_PORT))
server.listen(20)
print('Logger relay listening on %s:%s' % (LISTEN_HOST, LISTEN_PORT), flush=True)

while True:
    conn, _ = server.accept()
    threading.Thread(target=handle, args=(conn,), daemon=True).start()
