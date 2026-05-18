class Tile:
    def __init__(self, terrain):
        self.terrain = terrain
        self.civilization = None
        self.grow_timer = 0      # farm grow counter
        self.regrow_timer = 0    # forest / rock regrow counter

    def symbol(self):
        if self.terrain == 'water':   return '~'
        if self.terrain == 'farm':    return 'F'
        if self.terrain == 'ready':   return 'R'
        if self.terrain == 'forest':  return 'T'
        if self.terrain == 'rock':    return 'o'
        if self.terrain == 'fiber':   return 'i'
        if self.terrain == 'stump':   return 't'   # recently chopped
        if self.terrain == 'rubble':  return 'r'   # recently mined
        return '.'   # grass, food, seed hidden