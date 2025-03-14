import socket
import threading
import json
import time
import math
from virtual_laser_machine import VirtualLaserMachine

class Server:
    def __init__(self, host='localhost', port=12345):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.machine = VirtualLaserMachine()
        self.lock = threading.Lock()
        self.running = True
        self.clients = []
        self.movement_thread = None
        self.should_stop = False
        self.MAX_COORD = 250  # Максимальное значение координат

    def start(self):
        print("Сервер запущен...")
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                print(f"Подключение от {addr}")
                self.clients.append(client_socket)
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket,))
                client_thread.start()
            except OSError:
                break

    def broadcast_update(self):
        status = json.dumps(self.machine.get_status()) + "\n"
        for client in self.clients.copy():
            try:
                client.sendall(status.encode('utf-8'))
            except (ConnectionResetError, BrokenPipeError, OSError):
                self.clients.remove(client)

    def handle_movement(self, target_x, target_y):
        with self.lock:
            self.should_stop = False
            start_x = self.machine.x
            start_y = self.machine.y
            
            # Корректировка координат
            target_x = max(-self.MAX_COORD, min(target_x, self.MAX_COORD))
            target_y = max(-self.MAX_COORD, min(target_y, self.MAX_COORD))
            
            dx = target_x - start_x
            dy = target_y - start_y
            distance = math.hypot(dx, dy)
            
            if distance == 0:
                return

            steps = max(1, int(round(distance)))
            time_per_step = 1.0 / self.machine.speed
            step_x = dx / steps
            step_y = dy / steps

            current_line = []
            initial_laser_on = self.machine.laser_on

            if initial_laser_on:
                current_line.append((start_x, start_y))
                self.machine.history.append(current_line)

            for i in range(steps):
                if not self.running or self.should_stop:
                    break
                
                if (initial_laser_on and not self.machine.laser_on) or (not initial_laser_on and self.machine.laser_on):
                    break
                
                self.machine.x = start_x + step_x * (i + 1)
                self.machine.y = start_y + step_y * (i + 1)
                
                if initial_laser_on and current_line:
                    current_line.append((self.machine.x, self.machine.y))
                    self.machine.history[-1] = current_line.copy()
                
                self.broadcast_update()
                time.sleep(time_per_step)

            if initial_laser_on and current_line:
                current_line.append((self.machine.x, self.machine.y))

    def handle_client(self, client_socket):
        buffer = b""
        with client_socket:
            while self.running:
                try:
                    data = client_socket.recv(4096)
                    if not data:
                        break
                    buffer += data

                    while True:
                        msg_end = buffer.find(b"\n")
                        if msg_end == -1:
                            break

                        full_msg = buffer[:msg_end]
                        buffer = buffer[msg_end+1:]
                        response = self.process_command(full_msg.decode('utf-8'))
                        client_socket.sendall(response.encode('utf-8') + b"\n")

                except (ConnectionResetError, BrokenPipeError):
                    break
        print(f"Клиент отключен: {client_socket.getpeername()}")

    def process_command(self, command):
        try:
            parts = command.strip().split()
            if not parts:
                return json.dumps({'error': 'Пустая команда'})

            cmd = parts[0].upper()
            if cmd == 'MOVE':
                if len(parts) != 3:
                    return json.dumps({'error': 'Неверная команда MOVE'})
                x = float(parts[1])
                y = float(parts[2])
                
                # Корректировка координат
                x = max(-self.MAX_COORD, min(x, self.MAX_COORD))
                y = max(-self.MAX_COORD, min(y, self.MAX_COORD))
                
                if self.movement_thread and self.movement_thread.is_alive():
                    self.should_stop = True
                    self.movement_thread.join()
                
                self.movement_thread = threading.Thread(
                    target=self.handle_movement,
                    args=(x, y)
                )
                self.movement_thread.start()
                return json.dumps(self.machine.get_status())

            elif cmd == 'SPEED':
                if len(parts) != 2:
                    return json.dumps({'error': 'Неверная команда SPEED'})
                self.machine.speed = float(parts[1])
                return json.dumps(self.machine.get_status())

            elif cmd == 'LASER':
                if len(parts) != 2:
                    return json.dumps({'error': 'Неверная команда LASER'})
                self.machine.laser_on = parts[1].upper() == 'ON'
                return json.dumps(self.machine.get_status())

            elif cmd == 'CLEAR':
                self.machine.history = []
                self.broadcast_update()
                return json.dumps(self.machine.get_status())

            elif cmd == 'GET_STATUS':
                return json.dumps(self.machine.get_status())

            else:
                return json.dumps({'error': 'Неизвестная команда'})

        except Exception as e:
            return json.dumps({'error': str(e)})

    def shutdown(self):
        self.running = False
        self.server_socket.close()
        print("Сервер остановлен")

if __name__ == "__main__":
    server = Server()
    try:
        server.start()
    except KeyboardInterrupt:
        server.shutdown()