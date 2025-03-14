import sys
import socket
import json
import select
import time
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog
)
from PyQt5.QtGui import QImage, QPainter, QPen, QColor, QFont, QPainterPath
from PyQt5.QtCore import Qt, QTimer, QPoint, QPointF

class LaserViewer(QWidget):
    def __init__(self, parent=None, main_window=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setFixedSize(800, 600)
        self.image = QImage(800, 600, QImage.Format_RGB32)
        self.image.fill(Qt.white)
        self.zoom_level = 1.0
        self.base_grid_step = 50
        self.offset = QPointF(0, 0)
        self.drag_start = None
        self.x = 0.0
        self.y = 0.0
        self.laser_on = False
        self.history = []
        self.MAX_COORD = 250  # Максимальное значение координат

    def wheelEvent(self, event):
        old_zoom = self.zoom_level
        factor = 1.1 if event.angleDelta().y() > 0 else 0.9
        self.zoom_level = max(0.5, min(self.zoom_level * factor, 5.0))
        
        center = QPointF(400, 300)
        self.offset = (center + (self.offset - center) * old_zoom) / self.zoom_level
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            point = (QPointF(event.pos()) - self.offset) / self.zoom_level
            target_x = point.x() - 400
            target_y = 300 - point.y()
            
            # Ограничение координат
            target_x = max(-self.MAX_COORD, min(target_x, self.MAX_COORD))
            target_y = max(-self.MAX_COORD, min(target_y, self.MAX_COORD))
            
            self.main_window.move_to_target(target_x, target_y)
        elif event.button() == Qt.RightButton:
            self.drag_start = event.pos()

    def mouseMoveEvent(self, event):
        if self.drag_start:
            delta = event.pos() - self.drag_start
            self.offset += delta
            self.drag_start = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        self.drag_start = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(self.offset)
        painter.scale(self.zoom_level, self.zoom_level)
        painter.fillRect(0, 0, 800, 600, Qt.white)
        
        # Сетка
        grid_size = self.base_grid_step
        pen = QPen(QColor(220, 220, 220), 1)
        painter.setPen(pen)
        
        # Вертикальные линии (X: -250, -200, ..., +250)
        for i in range(-5, 6):
            x = 400 + i * grid_size
            painter.drawLine(x, 0, x, 600)
        
        # Горизонтальные линии (Y: -250, -200, ..., +250)
        for i in range(-5, 6):
            y = 300 + i * grid_size
            painter.drawLine(0, y, 800, y)
        
        # Оси координат
        pen = QPen(Qt.black, 2)
        painter.setPen(pen)
        painter.drawLine(400, 0, 400, 600)  # Y-axis
        painter.drawLine(0, 300, 800, 300)  # X-axis
        
        # Подписи координат
        font = QFont("Arial", 8)
        painter.setFont(font)
        for i in range(-5, 6):
            if i == 0: continue
            x = 400 + i * grid_size
            painter.drawText(x - 15, 315, f"{i*50}")
            y = 300 - i * grid_size
            painter.drawText(415, y + 5, f"{i*50}")

        # История линий
        pen = QPen(Qt.red, 2)
        painter.setPen(pen)
        for line in self.history:
            if len(line) > 1:
                path = QPainterPath()
                path.moveTo(400 + line[0][0], 300 - line[0][1])
                for point in line[1:]:
                    path.lineTo(400 + point[0], 300 - point[1])
                painter.drawPath(path)

        # Текущая позиция
        color = Qt.red if self.laser_on else Qt.blue
        painter.setPen(QPen(color, 6))
        painter.drawPoint(int(400 + self.x), int(300 - self.y))

    def load_image(self, image_path):
        img = QImage(image_path)
        img = img.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image = img.convertToFormat(QImage.Format_Grayscale8)
        self.update()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.host = 'localhost'
        self.port = 12345
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(1)
        self.buffer = b""
        self.MAX_COORD = 250  # Максимальное значение координат
        
        try:
            self.socket.connect((self.host, self.port))
        except (ConnectionRefusedError, socket.timeout):
            print("Ошибка подключения к серверу")
            sys.exit(1)

        self.init_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status)
        self.timer.start(50)

    def init_ui(self):
        self.setWindowTitle("Лазерный станок - Клиент")
        self.setGeometry(100, 100, 1000, 800)

        main_layout = QHBoxLayout()
        self.viewer = LaserViewer(main_window=self)
        main_layout.addWidget(self.viewer)

        control_panel = QVBoxLayout()

        zoom_panel = QHBoxLayout()
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.clicked.connect(lambda: self.set_zoom(1.1))
        zoom_panel.addWidget(zoom_in_btn)
        
        zoom_out_btn = QPushButton("-")
        zoom_out_btn.clicked.connect(lambda: self.set_zoom(0.9))
        zoom_panel.addWidget(zoom_out_btn)
        control_panel.addLayout(zoom_panel)

        self.coord_input_x = QLineEdit()
        self.coord_input_y = QLineEdit()
        self.coord_input_x.setPlaceholderText("X координата")
        self.coord_input_y.setPlaceholderText("Y координата")
        control_panel.addWidget(self.coord_input_x)
        control_panel.addWidget(self.coord_input_y)

        move_button = QPushButton("Переместить")
        move_button.clicked.connect(self.move_to_coordinates)
        control_panel.addWidget(move_button)

        self.speed_input = QLineEdit()
        self.speed_input.setPlaceholderText("Скорость (шаг/сек)")
        control_panel.addWidget(self.speed_input)

        set_speed_button = QPushButton("Установить скорость")
        set_speed_button.clicked.connect(self.set_speed)
        control_panel.addWidget(set_speed_button)

        self.laser_button = QPushButton("Включить лазер")
        self.laser_button.clicked.connect(self.toggle_laser)
        control_panel.addWidget(self.laser_button)

        clear_button = QPushButton("Очистить холст")
        clear_button.clicked.connect(self.clear_canvas)
        control_panel.addWidget(clear_button)

        load_image_button = QPushButton("Загрузить изображение")
        load_image_button.clicked.connect(self.load_image)
        control_panel.addWidget(load_image_button)

        scan_image_button = QPushButton("Сканировать изображение")
        scan_image_button.clicked.connect(self.scan_image)
        control_panel.addWidget(scan_image_button)

        self.status_label = QLabel()
        control_panel.addWidget(self.status_label)

        main_layout.addLayout(control_panel)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def set_zoom(self, factor):
        self.viewer.zoom_level *= factor
        self.viewer.zoom_level = max(0.5, min(self.viewer.zoom_level, 5.0))
        self.viewer.update()

    def move_to_target(self, x, y):
        x = max(-self.MAX_COORD, min(x, self.MAX_COORD))
        y = max(-self.MAX_COORD, min(y, self.MAX_COORD))
        self.coord_input_x.setText(f"{x:.1f}")
        self.coord_input_y.setText(f"{y:.1f}")
        self.safe_send(f"MOVE {x} {y}")

    def safe_send(self, command):
        try:
            self.socket.sendall(f"{command}\n".encode('utf-8'))
            return True
        except (BrokenPipeError, OSError):
            self.status_label.setText("Соединение потеряно")
            return False

    def process_buffer(self):
        while True:
            msg_end = self.buffer.find(b"\n")
            if msg_end == -1:
                break

            full_msg = self.buffer[:msg_end]
            self.buffer = self.buffer[msg_end+1:]

            try:
                status = json.loads(full_msg.decode('utf-8'))
                if 'error' in status:
                    continue
                
                self.viewer.x = status['x']
                self.viewer.y = status['y']
                self.viewer.laser_on = status['laser_on']
                self.viewer.history = status['history']
                self.laser_button.setText("Выключить лазер" if status['laser_on'] else "Включить лазер")
                
                self.status_label.setText(
                    f"Позиция: ({status['x']:.2f}, {status['y']:.2f})\n"
                    f"Лазер: {'ВКЛ' if status['laser_on'] else 'ВЫКЛ'}\n"
                    f"Скорость: {status['speed']} шаг/сек"
                )
                self.viewer.update()
                
            except json.JSONDecodeError:
                continue

    def update_status(self):
        if not self.safe_send("GET_STATUS"):
            return

        try:
            while True:
                ready = select.select([self.socket], [], [], 0.01)
                if not ready[0]:
                    break

                data = self.socket.recv(4096)
                if not data:
                    break
                self.buffer += data

            self.process_buffer()

        except (socket.timeout, ConnectionResetError):
            pass
        except Exception as e:
            print(f"Ошибка обновления: {e}")

    def move_to_coordinates(self):
        x = self.coord_input_x.text()
        y = self.coord_input_y.text()
        if x and y:
            x = max(-self.MAX_COORD, min(float(x), self.MAX_COORD))
            y = max(-self.MAX_COORD, min(float(y), self.MAX_COORD))
            self.safe_send(f"MOVE {x} {y}")

    def set_speed(self):
        speed = self.speed_input.text()
        if speed:
            self.safe_send(f"SPEED {speed}")

    def toggle_laser(self):
        new_state = 'OFF' if self.viewer.laser_on else 'ON'
        self.safe_send(f"LASER {new_state}")

    def clear_canvas(self):
        self.safe_send("CLEAR")

    def load_image(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "", 
            "Изображения (*.png *.jpg *.bmp);;Все файлы (*)", options=options)
        if file_name:
            self.viewer.load_image(file_name)

    def scan_image(self):
        if self.viewer.image.isNull():
            self.status_label.setText("Изображение не загружено")
            return

        threshold = 128
        step_size = 1
        delay = 0.1
        width = self.viewer.image.width()
        height = self.viewer.image.height()

        self.safe_send("MOVE 0 0")
        self.safe_send("LASER OFF")
        time.sleep(delay)

        for y in range(0, height, step_size):
            active_lines = []
            start_x = None

            for x in range(0, width, step_size):
                color = self.viewer.image.pixelColor(x, y)
                brightness = color.red()

                if brightness < threshold:
                    if start_x is None:
                        start_x = x
                else:
                    if start_x is not None:
                        active_lines.append((start_x, x - step_size))
                        start_x = None

            if start_x is not None:
                active_lines.append((start_x, width - step_size))

            for line in active_lines:
                start_x, end_x = line
                # Преобразование координат изображения в системные
                target_x = start_x - width//2
                target_y = height//2 - y
                target_x = max(-self.MAX_COORD, min(target_x, self.MAX_COORD))
                target_y = max(-self.MAX_COORD, min(target_y, self.MAX_COORD))
                
                self.safe_send(f"MOVE {target_x} {target_y}")
                time.sleep(delay)
                self.safe_send("LASER ON")
                time.sleep(delay)
                self.safe_send(f"MOVE {end_x - width//2} {target_y}")
                time.sleep(delay)
                self.safe_send("LASER OFF")
                time.sleep(delay)

            self.status_label.setText(f"Сканирование: {(y+1)/height*100:.1f}%")

        self.status_label.setText("Сканирование завершено")

    def closeEvent(self, event):
        self.socket.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())