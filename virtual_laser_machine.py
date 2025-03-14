class VirtualLaserMachine:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.laser_on = False
        self.speed = 100.0  # Шагов в секунду
        self.history = []   # Хранит списки точек для каждой линии [[(x1,y1), (x2,y2)], ...]

    def get_status(self):
        return {
            'x': self.x,
            'y': self.y,
            'laser_on': self.laser_on,
            'speed': self.speed,
            'history': self.history.copy()
        }