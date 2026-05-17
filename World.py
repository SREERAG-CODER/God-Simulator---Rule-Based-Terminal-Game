import random
from Tile import Tile
from Civilization import Person

class World:
    def __init__ (self, width, height):
        self.width = width
        self.height = height
        self.grid = [[Tile('grass') for _ in range(width)] for _ in range(height)]
        self.generate_terrain()

    def generate_terrain(self):
        for _ in range(4):  # 4 water patches
            cx = random.randint(3, self.width - 4) # Circle Formula Method
            cy = random.randint(3, self.height - 4)
            radius = random.randint(2, 4)  # patch size

        
            for y in range(self.height):
                for x in range(self.width):
                # check if this tile is within the circle
                    if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                        self.grid[y][x].terrain = "water"
    
    def spawn_person(self, name):
        while True:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            tile = self.grid[y][x]
            if tile.terrain == 'grass' and tile.civilization is None:
                person = Person(name, x, y)
                tile.civilization = person
            return person

    def display(self):
        for row in self.grid:
            print(" ".join(
                tile.civilization.symbol if tile.civilization else tile.symbol()
                for tile in row
            ))