import random
from collections import deque

CHILD_NAMES = [
    "Cain", "Abel", "Seth", "Aya", "Lila", "Ren", "Kael", "Mira",
    "Theo", "Nora", "Eli", "Zara", "Ivan", "Sena", "Oryn", "Deva"
]

class Person:
    def __init__(self, name, x, y, intelligence=10):
        self.name = name
        self.x = x
        self.y = y
        self.age = 0
        self.health = 100
        self.hunger = 100
        self.intelligence = intelligence
        self.symbol = 'P'
        self.isAlive = True
        self.inventory = []
        self.max_inventory = 25
        self.has_farm = False
        self.farm_x = None
        self.farm_y = None
        self.farm_full = False
        self.current_task = 'roaming'
        self.birth_cooldown = 0       # ticks remaining before can reproduce again

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
        if self.hunger > 50 and self.health >= 50:
            return

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

    def tick_cooldowns(self):
        if self.birth_cooldown > 0:
            self.birth_cooldown -= 1

    # --- BFS Pathfinder ---
    def _find_path_step(self, world, target_x, target_y):
        """
        BFS from current position to (target_x, target_y).
        Returns the (dx, dy) of the first step along the shortest
        walkable path, or None if no path exists.
        Water is never passable. The target tile itself is allowed
        even if currently occupied.
        """
        if self.x == target_x and self.y == target_y:
            return None

        queue = deque()
        queue.append((self.x, self.y, []))
        visited = {(self.x, self.y)}

        while queue:
            cx, cy, path = queue.popleft()
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < world.width and 0 <= ny < world.height):
                    continue
                if (nx, ny) in visited:
                    continue

                tile = world.grid[ny][nx]
                at_target = (nx == target_x and ny == target_y)
                passable = (
                    tile.terrain != 'water' and
                    (tile.civilization is None or at_target)
                )
                if not passable:
                    continue

                new_path = path + [(nx, ny)]
                if at_target:
                    first = new_path[0]
                    return (first[0] - self.x, first[1] - self.y)

                visited.add((nx, ny))
                queue.append((nx, ny, new_path))

        return None

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

                        # Kill if already adjacent
                        if abs(self.x - target_x) <= 1 and abs(self.y - target_y) <= 1:
                            if self.x != target_x or self.y != target_y:
                                animal.isAlive = False
                                world.grid[target_y][target_x].civilization = None
                                world.animals.remove(animal)
                                self.add_to_inventory('meat')
                                self.current_task = 'roaming'
                                return

                        # BFS toward animal
                        step = self._find_path_step(world, target_x, target_y)
                        if step:
                            ox, oy = step
                            new_x = self.x + ox
                            new_y = self.y + oy
                            next_tile = world.grid[new_y][new_x]
                            if new_x == target_x and new_y == target_y:
                                animal.isAlive = False
                                world.grid[target_y][target_x].civilization = None
                                world.animals.remove(animal)
                                self.add_to_inventory('meat')
                                self.current_task = 'roaming'
                                return
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

                if not (0 <= px < world.width and 0 <= py < world.height):
                    continue

                tile = world.grid[py][px]
                if tile.terrain != 'ready':
                    continue

                if self.x == px and self.y == py:
                    tile.terrain = 'grass'
                    tile.grow_timer = 0
                    self.add_to_inventory('harvested')
                    self.add_to_inventory('seed')
                    self.current_task = 'planting'
                    self.farm_full = False   # freed tile — can plant again
                    return True

                step = self._find_path_step(world, px, py)
                if step is None:
                    continue

                ox, oy = step
                new_x = self.x + ox
                new_y = self.y + oy
                next_tile = world.grid[new_y][new_x]

                if next_tile.terrain in ('grass', 'farm', 'ready') and next_tile.civilization is None:
                    world.grid[self.y][self.x].civilization = None
                    self.x = new_x
                    self.y = new_y
                    world.grid[self.y][self.x].civilization = self
                    self.current_task = 'harvesting'
                    return True

        return False

    # --- Food Sharing ---
    def try_share_food(self, world):
        """
        If this person is well-fed (hunger > 70) and has surplus edible food,
        give one item to any adjacent starving person (hunger < 30).
        Priority: most starving neighbour first.
        """
        if self.hunger <= 50:
            return
        # Collect edible items we can spare (never share seeds)
        shareable = [i for i in ('harvested', 'food', 'meat') if self.has_item(i)]
        if not shareable:
            return

        # Find adjacent starving people, sorted by hunger ascending (hungriest first)
        neighbours = []
        for other in world.people:
            if other is self or not other.isAlive:
                continue
            if other.hunger >= 30:
                continue
            dist = abs(self.x - other.x) + abs(self.y - other.y)
            if dist <= 1:
                neighbours.append(other)

        if not neighbours:
            return

        neighbours.sort(key=lambda p: p.hunger)
        recipient = neighbours[0]

        # Hand over the best available item
        for item in ('harvested', 'meat', 'food'):
            if self.has_item(item):
                self.remove_item(item)
                recipient.add_to_inventory(item)
                self.current_task = 'sharing'
                return

    # --- Seek Partner ---
    def seek_partner(self, world):
        """
        When this person is reproduction-ready but no partner is close enough,
        actively BFS-walk one step toward the nearest eligible partner.
        Returns True if a step was taken.
        """
        if self.birth_cooldown > 0:
            return False
        if self.health < 70 or self.hunger < 40 or self.intelligence < 50:
            return False
        if self.age < 15:
            return False
        if len(world.people) >= world.population_cap:
            return False

        # Find nearest eligible partner
        best = None
        best_dist = float('inf')
        for other in world.people:
            if other is self or not other.isAlive:
                continue
            if other.birth_cooldown > 0:
                continue
            if other.health < 70 or other.hunger < 40 or other.intelligence < 50:
                continue
            if other.age < 15:
                continue
            dist = abs(self.x - other.x) + abs(self.y - other.y)
            if dist <= 2:
                return False  # already close enough — let try_reproduce handle it
            if dist < best_dist:
                best_dist = dist
                best = other

        if best is None:
            return False

        step = self._find_path_step(world, best.x, best.y)
        if step is None:
            return False

        ox, oy = step
        new_x, new_y = self.x + ox, self.y + oy
        tile = world.grid[new_y][new_x]
        if tile.terrain in ('grass', 'food', 'seed') and tile.civilization is None:
            if tile.terrain == 'food':
                self.add_to_inventory('food')
                tile.terrain = 'grass'
            world.grid[self.y][self.x].civilization = None
            self.x, self.y = new_x, new_y
            world.grid[self.y][self.x].civilization = self
            self.current_task = 'seeking'
            return True

        return False

    # --- Reproduction ---
    def try_reproduce(self, world):
        """
        Scan nearby people for a healthy, ready partner.
        Conditions (both parents must meet):
          - health >= 70, hunger >= 60, intelligence >= 50
          - birth_cooldown == 0
          - within Manhattan distance 2
        On success: spawns a child adjacent to self, applies 150-tick
        cooldown to both parents, returns the new Person.
        Returns None if no birth occurred.
        """
        if not self.isAlive:
            return None
        if self.birth_cooldown > 0:
            return None
        if self.health < 70 or self.hunger < 40:
            return None
        if self.intelligence < 50:
            return None
        if self.age < 15:
            return None
        if len(world.people) >= world.population_cap:
            return None

        for other in world.people:
            if other is self:
                continue
            if not other.isAlive:
                continue
            if other.birth_cooldown > 0:
                continue
            if other.health < 70 or other.hunger < 40:
                continue
            if other.intelligence < 50:
                continue
            if other.age < 15:
                continue

            dist = abs(self.x - other.x) + abs(self.y - other.y)
            if dist > 2:
                continue

            # Find a free adjacent grass tile for the child
            child_pos = None
            for dx, dy in random.sample([(0, -1), (0, 1), (-1, 0), (1, 0)], 4):
                cx, cy = self.x + dx, self.y + dy
                if 0 <= cx < world.width and 0 <= cy < world.height:
                    tile = world.grid[cy][cx]
                    if tile.terrain == 'grass' and tile.civilization is None:
                        child_pos = (cx, cy)
                        break

            if child_pos is None:
                continue  # no room near this parent — try next candidate

            # Name: pick unused name from pool
            used_names = {p.name for p in world.people}
            available = [n for n in CHILD_NAMES if n not in used_names]
            child_name = available[0] if available else f"Child{len(world.people)}"

            # Intelligence: average of parents ± small variance
            child_intel = int((self.intelligence + other.intelligence) / 2)
            child_intel = max(10, min(200, child_intel + random.randint(-10, 10)))

            # Cooldown both parents
            self.birth_cooldown = 150
            other.birth_cooldown = 150

            # Place child
            cx, cy = child_pos
            child = Person(child_name, cx, cy, intelligence=child_intel)
            world.grid[cy][cx].civilization = child
            world.people.append(child)

            return child

        return None

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
        directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]
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