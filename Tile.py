class Tile:
    def __init__(self, terrain):
        self.terrain = terrain
        self.civilization = None
        self.grow_timer = 0  # for farm tiles

    def symbol(self):
        if self.terrain == 'water':
            return '~'
        elif self.terrain == 'farm':
            return 'F'
        elif self.terrain == 'ready':
            return 'R'
        else:
            return '.'  # grass, food, seed all hidden