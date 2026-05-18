import random

class Animal:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.health = 30
        self.symbol = 'A'
        self.isAlive = True

    def move(self, world):
        directions = [(0,-1),(0,1),(-1,0),(1,0)]
        random.shuffle(directions)

        for dx, dy in directions:
            new_x = self.x + dx
            new_y = self.y + dy

            if 0 <= new_x < world.width and 0 <= new_y < world.height:
                tile = world.grid[new_y][new_x]
                if tile.terrain == 'grass' and tile.civilization is None:
                    world.grid[self.y][self.x].civilization = None
                    self.x = new_x
                    self.y = new_y
                    world.grid[self.y][self.x].civilization = self
                    break