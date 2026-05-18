import random
from Tile import Tile
from Civilization import Person
from Animal import Animal

class World:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.grid = [[Tile('grass') for _ in range(width)] for _ in range(height)]
        self.generate_terrain()
        self.spawn_animals()

    def generate_terrain(self):
        # water blobs
        for _ in range(4):
            cx = random.randint(3, self.width - 4)
            cy = random.randint(3, self.height - 4)
            radius = random.randint(2, 4)
            for y in range(self.height):
                for x in range(self.width):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                        self.grid[y][x].terrain = 'water'

        # hidden food
        food_count = 0
        while food_count < 30:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            if self.grid[y][x].terrain == 'grass':
                self.grid[y][x].terrain = 'food'
                food_count += 1

        # hidden seeds
        seed_count = 0
        while seed_count < 20:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            if self.grid[y][x].terrain == 'grass':
                self.grid[y][x].terrain = 'seed'
                seed_count += 1

    def grow_farms(self):
        for row in self.grid:
            for tile in row:
                if tile.terrain == 'farm':
                    tile.grow_timer += 1
                    if tile.grow_timer >= 40:
                        tile.terrain = 'ready'
                        tile.grow_timer = 0

    def spawn_animals(self, count=5):
        self.animals = []
        spawned = 0
        attempts = 0
        while spawned < count and attempts < 1000:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            if self.grid[y][x].terrain == 'grass' and self.grid[y][x].civilization is None:
                animal = Animal(x, y)
                self.grid[y][x].civilization = animal
                self.animals.append(animal)
                spawned += 1
            attempts += 1

    def respawn_animals(self):
        alive = sum(1 for a in self.animals if a.isAlive)
        if alive < 3:
            attempts = 0
            while attempts < 1000:
                x = random.randint(0, self.width - 1)
                y = random.randint(0, self.height - 1)
                if self.grid[y][x].terrain == 'grass' and self.grid[y][x].civilization is None:
                    animal = Animal(x, y)
                    self.grid[y][x].civilization = animal
                    self.animals.append(animal)
                    break
                attempts += 1

    def update_animals(self, tick):
        if tick % 4 == 0:
            for animal in self.animals:
                if animal.isAlive:
                    animal.move(self)

    def spawn_person(self, name):
        while True:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            if self.grid[y][x].terrain == 'grass' and self.grid[y][x].civilization is None:
                person = Person(name, x, y)
                self.grid[y][x].civilization = person
                return person

    def display(self):
        for row in self.grid:
            print(" ".join(
                tile.civilization.symbol if tile.civilization else tile.symbol()
                for tile in row
            ))