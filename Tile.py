class Tile:
    def __init__(self, terrain):
        self.terrain = terrain
        self.civilization = None

    def symbol(self):
        if self.terrain == 'water':
            return '~'
        else:
            return '.'  # everything else is grass