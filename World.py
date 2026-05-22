import random
from Tile import Tile
from Civilization import Person
from Animal import Animal
from Building import BuildSite, Hut, Storehouse

# ── Population cap constants ──────────────────────────────────────────────────
BASE_POP_CAP          = 10    # starting cap before any buildings
POP_CAP_PER_HUT       = 5    # each completed hut adds this
# Storehouse food scaling: for every FOOD_PER_POP food stored across all
# storehouses, the cap rises by 1 (up to STOREHOUSE_POP_CAP_MAX bonus)
FOOD_PER_POP          = 8
STOREHOUSE_POP_CAP_MAX = 30


class World:
    def __init__(self, width, height, population_cap=BASE_POP_CAP):
        self.width          = width
        self.height         = height
        self.grid           = [[Tile('grass') for _ in range(width)] for _ in range(height)]
        self.people         = []
        self.animals        = []

        # Base cap is stored separately so we can recompute dynamically
        self._base_pop_cap  = population_cap
        self._hut_pop_bonus = 0          # cumulative bonus from completed huts
        self.population_cap = population_cap   # recomputed each tick

        # Buildings
        self.huts           = []        # list of Hut
        self.storehouses    = []        # list of Storehouse
        self.build_sites    = []        # list of BuildSite (in-progress)

        self.generate_terrain()
        self.spawn_animals()

    # ── Population cap ───────────────────────────────────────────────────────
    def recompute_population_cap(self):
        """
        Call once per tick.  Cap = base + hut bonus + storehouse food bonus.
        Storehouse bonus: floor(total_stored_food / FOOD_PER_POP), capped at
        STOREHOUSE_POP_CAP_MAX.  This means keeping storehouses well-stocked
        meaningfully raises how many people the world can sustain.
        """
        total_food = sum(sh.food_count() for sh in self.storehouses)
        food_bonus = min(STOREHOUSE_POP_CAP_MAX, total_food // FOOD_PER_POP)
        self.population_cap = self._base_pop_cap + self._hut_pop_bonus + food_bonus

    def storehouse_food_bonus(self):
        """Return current food-driven population bonus (for display)."""
        total_food = sum(sh.food_count() for sh in self.storehouses)
        return min(STOREHOUSE_POP_CAP_MAX, total_food // FOOD_PER_POP)

    # ── Terrain generation ───────────────────────────────────────────────────
    def generate_terrain(self):
        # Water blobs
        for _ in range(4):
            cx     = random.randint(3, self.width - 4)
            cy     = random.randint(3, self.height - 4)
            radius = random.randint(2, 4)
            for y in range(self.height):
                for x in range(self.width):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                        self.grid[y][x].terrain = 'water'

        # Forest clusters (wood source)
        for _ in range(6):
            cx     = random.randint(3, self.width - 4)
            cy     = random.randint(3, self.height - 4)
            radius = random.randint(2, 4)
            for y in range(self.height):
                for x in range(self.width):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                        if self.grid[y][x].terrain == 'grass':
                            self.grid[y][x].terrain = 'forest'

        # Rock clusters (stone source)
        for _ in range(4):
            cx     = random.randint(3, self.width - 4)
            cy     = random.randint(3, self.height - 4)
            radius = random.randint(1, 3)
            for y in range(self.height):
                for x in range(self.width):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                        if self.grid[y][x].terrain == 'grass':
                            self.grid[y][x].terrain = 'rock'

        # Fiber patches
        fiber_count = 0
        while fiber_count < 60:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            if self.grid[y][x].terrain == 'grass':
                self.grid[y][x].terrain = 'fiber'
                fiber_count += 1

        # Hidden food
        food_count = 0
        while food_count < 100:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            if self.grid[y][x].terrain == 'grass':
                self.grid[y][x].terrain = 'food'
                food_count += 1

        # Hidden seeds
        seed_count = 0
        while seed_count < 60:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            if self.grid[y][x].terrain == 'grass':
                self.grid[y][x].terrain = 'seed'
                seed_count += 1

    def seed_food_near(self, cx, cy, radius=6, count=8):
        placed   = 0
        attempts = 0
        while placed < count and attempts < 500:
            x = cx + random.randint(-radius, radius)
            y = cy + random.randint(-radius, radius)
            if 0 <= x < self.width and 0 <= y < self.height:
                if self.grid[y][x].terrain == 'grass':
                    self.grid[y][x].terrain = 'food'
                    placed += 1
            attempts += 1

    # ── Resource regrowth ────────────────────────────────────────────────────
    def update_regrowth(self):
        for row in self.grid:
            for tile in row:
                if tile.terrain == 'stump':
                    tile.regrow_timer += 1
                    if tile.regrow_timer >= 200:
                        tile.terrain      = 'forest'
                        tile.regrow_timer = 0
                elif tile.terrain == 'rubble':
                    tile.regrow_timer += 1
                    if tile.regrow_timer >= 400:
                        tile.terrain      = 'rock'
                        tile.regrow_timer = 0
                elif tile.terrain == 'fiber_spent':
                    tile.regrow_timer += 1
                    if tile.regrow_timer >= 100:
                        tile.terrain      = 'fiber'
                        tile.regrow_timer = 0

    # ── Farm growth ──────────────────────────────────────────────────────────
    def grow_farms(self):
        for row in self.grid:
            for tile in row:
                if tile.terrain == 'farm':
                    tile.grow_timer += 1
                    if tile.grow_timer >= 40:
                        tile.terrain    = 'ready'
                        tile.grow_timer = 0

    # ── Buildings ────────────────────────────────────────────────────────────
    def add_build_site(self, kind, x, y):
        site = BuildSite(kind, x, y)
        self.build_sites.append(site)
        self.grid[y][x].civilization = site
        return site

    def complete_build_site(self, site):
        """Convert a finished BuildSite into the real building."""
        x, y = site.x, site.y
        self.build_sites.remove(site)

        if site.kind == 'hut':
            building = Hut(x, y)
            self.huts.append(building)
            # Accumulate hut bonus separately; recompute_population_cap will apply it
            self._hut_pop_bonus += Hut.POP_BONUS
            self.grid[y][x].civilization = building
        elif site.kind == 'storehouse':
            building = Storehouse(x, y)
            self.storehouses.append(building)
            self.grid[y][x].civilization = building

        # Immediately recompute so the cap is current
        self.recompute_population_cap()

    def apply_hut_healing(self):
        for hut in self.huts:
            hut.apply_healing(self)

    # ── Storehouse helpers ───────────────────────────────────────────────────
    def nearest_storehouse(self, x, y, max_dist=30):
        best      = None
        best_dist = max_dist + 1
        for sh in self.storehouses:
            d = abs(sh.x - x) + abs(sh.y - y)
            if d < best_dist:
                best_dist = d
                best      = sh
        return best

    def nearest_hut(self, x, y, max_dist=30):
        best      = None
        best_dist = max_dist + 1
        for hut in self.huts:
            d = abs(hut.x - x) + abs(hut.y - y)
            if d < best_dist:
                best_dist = d
                best      = hut
        return best

    def nearest_build_site(self, kind, x, y, max_dist=40):
        best      = None
        best_dist = max_dist + 1
        for site in self.build_sites:
            if site.kind != kind:
                continue
            d = abs(site.x - x) + abs(site.y - y)
            if d < best_dist:
                best_dist = d
                best      = site
        return best

    def total_stored_food(self):
        return sum(sh.food_count() for sh in self.storehouses)

    # ── Animals ──────────────────────────────────────────────────────────────
    def spawn_animals(self, count=12):
        spawned  = 0
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
        if alive < 6:
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

    # ── People ───────────────────────────────────────────────────────────────
    def spawn_person(self, name, intelligence=10):
        attempts = 0
        while attempts < 1000:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            if self.grid[y][x].terrain == 'grass' and self.grid[y][x].civilization is None:
                person = Person(name, x, y, intelligence=intelligence)
                self.grid[y][x].civilization = person
                self.people.append(person)
                return person
            attempts += 1
        raise RuntimeError("Could not find a free tile to spawn person")

    def prune_dead(self):
        alive = []
        for p in self.people:
            if p.isAlive:
                alive.append(p)
            else:
                if self.grid[p.y][p.x].civilization is p:
                    self.grid[p.y][p.x].civilization = None
        self.people = alive

    # ── Display ──────────────────────────────────────────────────────────────
    def display(self):
        for row in self.grid:
            print(" ".join(
                tile.civilization.symbol if tile.civilization else tile.symbol()
                for tile in row
            ))