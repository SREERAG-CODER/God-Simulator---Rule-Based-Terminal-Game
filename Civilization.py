import random

class Person:
    def __init__(self, name, x, y):
        self.name = name
        self.x = x
        self.y = y
        self.age = 0
        self.health = 100
        self.hunger = 100
        self.intelligence = 10
        self.symbol = 'P'
        self.isAlive = True
        self.inventory = []
        self.max_inventory = 25
        self.has_farm = False
        self.farm_x = None
        self.farm_y = None
        self.farm_full = False
        self.current_task = 'roaming'

    # --- Inventory ---
    def add_to_inventory(self, item):
        if len(self.inventory) < self.max_inventory:
            self.inventory.append(item)
            return True
        return False

    def has_item(self, item_type):
        return any(i == item_type for i in self.inventory)

    def remove_item(self, item_type):
        if item_type in self.inventory:
            self.inventory.remove(item_type)
            return True
        return False

    def inventory_count(self, item_type):
        return self.inventory.count(item_type)

    def has_edible_food(self):
        return (self.has_item('food') or
                self.has_item('harvested') or
                self.has_item('meat'))

    # --- Eating ---
    def try_eat(self):
        # eat if hunger below 30 OR health below 30
        if self.hunger > 30 and self.health >= 30:
            return

        # priority: harvested → food → meat
        if self.has_item('harvested'):
            self.remove_item('harvested')
            self.hunger = min(100, self.hunger + 50)
            self.health = min(100, self.health + 20)
            return

        if self.has_item('food'):
            self.remove_item('food')
            self.hunger = min(100, self.hunger + 40)
            self.health = min(100, self.health + 15)
            return

        if self.has_item('meat'):
            self.remove_item('meat')
            self.hunger = min(100, self.hunger + 80)
            self.health = min(100, self.health + 20)
            return

        # seeds are NEVER eaten

    # --- Hunger & Health ---
    def update_hunger(self, tick):
        if tick % 5 == 0:
            self.hunger -= 5

        if self.hunger <= 0:
            self.hunger = 0
            self.health -= 10

        if self.health <= 0:
            self.isAlive = False
            return

        self.try_eat()

    def age_up(self, tick):
        if tick % 40 == 0:
            self.age += 1

    def intelligence_gain(self, tick):
        if self.intelligence < 200:
            if tick % 30 == 0:
                self.intelligence += 5

    # --- Hunting ---
    def hunt(self, world):
        if not self.isAlive:
            return
        if self.intelligence < 30:
            return

        self.current_task = 'hunting'
        radius = 9 if self.intelligence >= 60 else 6

        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                target_x = self.x + dx
                target_y = self.y + dy

                if 0 <= target_x < world.width and 0 <= target_y < world.height:
                    tile = world.grid[target_y][target_x]

                    if tile.civilization is not None and tile.civilization.symbol == 'A':
                        animal = tile.civilization

                        step_x = 0
                        step_y = 0
                        if self.x < target_x: step_x = 1
                        elif self.x > target_x: step_x = -1
                        if self.y < target_y: step_y = 1
                        elif self.y > target_y: step_y = -1

                        new_x = self.x + step_x
                        new_y = self.y + step_y

                        if 0 <= new_x < world.width and 0 <= new_y < world.height:
                            next_tile = world.grid[new_y][new_x]

                            # kill if stepping on same tile
                            if new_x == target_x and new_y == target_y:
                                animal.isAlive = False
                                world.grid[target_y][target_x].civilization = None
                                world.animals.remove(animal)
                                self.add_to_inventory('meat')  # stored, eaten when hungry
                                self.current_task = 'roaming'
                                return

                            # move toward animal
                            if next_tile.terrain == 'grass' and next_tile.civilization is None:
                                world.grid[self.y][self.x].civilization = None
                                self.x = new_x
                                self.y = new_y
                                world.grid[self.y][self.x].civilization = self
                                return

    # --- Seed Collection ---
    def try_collect_seed(self, world):
        if self.farm_full:
            return
        tile = world.grid[self.y][self.x]
        if tile.terrain == 'seed':
            if self.add_to_inventory('seed'):
                tile.terrain = 'grass'

    # --- Planting ---
    def try_plant(self, world):
        if not self.has_item('seed'):
            return
        if self.intelligence < 40:
            return

        if not self.has_farm:
            self.has_farm = True
            self.farm_x = self.x
            self.farm_y = self.y

        for dy in range(-5, 6):
            for dx in range(-5, 6):
                px = self.farm_x + dx
                py = self.farm_y + dy

                if 0 <= px < world.width and 0 <= py < world.height:
                    if (dx**2 + dy**2) <= 25:
                        tile = world.grid[py][px]
                        if tile.terrain == 'grass' and tile.civilization is None:
                            tile.terrain = 'farm'
                            tile.grow_timer = 0
                            self.remove_item('seed')
                            self.current_task = 'farming'
                            return

        self.farm_full = True

    # --- Harvesting ---
    def try_harvest(self, world):
        if not self.has_farm:
            return False

        for dy in range(-5, 6):
            for dx in range(-5, 6):
                px = self.farm_x + dx
                py = self.farm_y + dy

                if 0 <= px < world.width and 0 <= py < world.height:
                    tile = world.grid[py][px]
                    if tile.terrain == 'ready':
                        # on the tile — harvest!
                        if self.x == px and self.y == py:
                            tile.terrain = 'grass'
                            tile.grow_timer = 0
                            self.add_to_inventory('harvested')
                            self.add_to_inventory('seed')
                            self.current_task = 'planting'
                            return True

                        else:
                            # try multiple directions to get around obstacles
                            step_x = 0
                            step_y = 0
                            if self.x < px: step_x = 1
                            elif self.x > px: step_x = -1
                            if self.y < py: step_y = 1
                            elif self.y > py: step_y = -1

                            options = [
                                (step_x, step_y),
                                (step_x, 0),
                                (0, step_y),
                                (-step_x, step_y),
                                (step_x, -step_y),
                            ]

                            for ox, oy in options:
                                if ox == 0 and oy == 0:
                                    continue
                                new_x = self.x + ox
                                new_y = self.y + oy
                                if 0 <= new_x < world.width and 0 <= new_y < world.height:
                                    next_tile = world.grid[new_y][new_x]
                                    if next_tile.terrain in ('grass', 'farm', 'ready') and next_tile.civilization is None:
                                        world.grid[self.y][self.x].civilization = None
                                        self.x = new_x
                                        self.y = new_y
                                        world.grid[self.y][self.x].civilization = self
                                        self.current_task = 'harvesting'
                                        return True
        return False

    # --- Check ready farms exist ---
    def has_ready_farm(self, world):
        if not self.has_farm:
            return False
        for dy in range(-5, 6):
            for dx in range(-5, 6):
                px = self.farm_x + dx
                py = self.farm_y + dy
                if 0 <= px < world.width and 0 <= py < world.height:
                    if world.grid[py][px].terrain == 'ready':
                        return True
        return False

    # --- Movement ---
    def move(self, world, tick):
        if not self.isAlive:
            return

        self.current_task = 'roaming'
        directions = [(0,-1),(0,1),(-1,0),(1,0)]
        random.shuffle(directions)

        for dx, dy in directions:
            new_x = self.x + dx
            new_y = self.y + dy

            if 0 <= new_x < world.width and 0 <= new_y < world.height:
                tile = world.grid[new_y][new_x]
                if tile.terrain in ('grass', 'food', 'seed') and tile.civilization is None:

                    if tile.terrain == 'food':
                        self.add_to_inventory('food')
                        tile.terrain = 'grass'

                    world.grid[self.y][self.x].civilization = None
                    self.x = new_x
                    self.y = new_y
                    world.grid[self.y][self.x].civilization = self
                    break