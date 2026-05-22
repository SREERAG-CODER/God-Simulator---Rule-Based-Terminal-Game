import random
from Tile import Tile
from Civilization import Person
from Animal import Animal
from Building import BuildSite, Hut, Storehouse

# ── Population cap constants ──────────────────────────────────────────────────
BASE_POP_CAP           = 10
POP_CAP_PER_HUT        = 5
FOOD_PER_POP           = 8
STOREHOUSE_POP_CAP_MAX = 30


class World:
    def __init__(self, width, height, population_cap=BASE_POP_CAP):
        self.width          = width
        self.height         = height
        self.grid           = [[Tile('grass') for _ in range(width)] for _ in range(height)]
        self.people         = []
        self.animals        = []

        self._base_pop_cap  = population_cap
        self._hut_pop_bonus = 0
        self.population_cap = population_cap

        # Buildings
        self.huts           = []
        self.storehouses    = []
        self.build_sites    = []

        # ── King / governance ─────────────────────────────────────────────
        self.king              = None    # King instance or None
        self.council           = []      # list of Person during interregnum
        self.starvation_count  = 0       # cumulative starving-ticks this reign
        self.succession_log    = []      # (tick, name, reason) tuples
        self._king_check_done  = False   # first-tick crown flag

        self.generate_terrain()
        self.spawn_animals()

    # ── Population cap ───────────────────────────────────────────────────────
    def recompute_population_cap(self):
        total_food = sum(sh.food_count() for sh in self.storehouses)
        food_bonus = min(STOREHOUSE_POP_CAP_MAX, total_food // FOOD_PER_POP)
        self.population_cap = self._base_pop_cap + self._hut_pop_bonus + food_bonus

    def storehouse_food_bonus(self):
        total_food = sum(sh.food_count() for sh in self.storehouses)
        return min(STOREHOUSE_POP_CAP_MAX, total_food // FOOD_PER_POP)

    # ── Terrain generation ───────────────────────────────────────────────────
    def generate_terrain(self):
        for _ in range(4):
            cx     = random.randint(3, self.width - 4)
            cy     = random.randint(3, self.height - 4)
            radius = random.randint(2, 4)
            for y in range(self.height):
                for x in range(self.width):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                        self.grid[y][x].terrain = 'water'

        for _ in range(6):
            cx     = random.randint(3, self.width - 4)
            cy     = random.randint(3, self.height - 4)
            radius = random.randint(2, 4)
            for y in range(self.height):
                for x in range(self.width):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                        if self.grid[y][x].terrain == 'grass':
                            self.grid[y][x].terrain = 'forest'

        for _ in range(4):
            cx     = random.randint(3, self.width - 4)
            cy     = random.randint(3, self.height - 4)
            radius = random.randint(1, 3)
            for y in range(self.height):
                for x in range(self.width):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                        if self.grid[y][x].terrain == 'grass':
                            self.grid[y][x].terrain = 'rock'

        fiber_count = 0
        while fiber_count < 60:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            if self.grid[y][x].terrain == 'grass':
                self.grid[y][x].terrain = 'fiber'
                fiber_count += 1

        food_count = 0
        while food_count < 100:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            if self.grid[y][x].terrain == 'grass':
                self.grid[y][x].terrain = 'food'
                food_count += 1

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
        x, y = site.x, site.y
        self.build_sites.remove(site)

        if site.kind == 'hut':
            building = Hut(x, y)
            self.huts.append(building)
            self._hut_pop_bonus += Hut.POP_BONUS
            self.grid[y][x].civilization = building
        elif site.kind == 'storehouse':
            building = Storehouse(x, y)
            self.storehouses.append(building)
            self.grid[y][x].civilization = building

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

    # ── King / governance ────────────────────────────────────────────────────
    def appoint_king(self, tick_num):
        """
        Crown the living person with the highest intelligence.
        Called once when population first reaches 2+.
        """
        from King import King
        candidates = [p for p in self.people if p.isAlive]
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.intelligence, reverse=True)
        chosen     = candidates[0]
        self.king  = King(chosen, tick_num)
        self.succession_log.append((tick_num, chosen.name, 'crowned'))
        return self.king

    def update_king(self, tick_num):
        """
        Called every tick.  Handles:
          • First-time coronation
          • King death / overthrow → form council → elect successor
          • Loyalty drift
          • King's own governance tick
        """
        from King import King, update_loyalties, form_council, elect_new_king

        # ── First coronation ──────────────────────────────────────────────
        if self.king is None and not self._king_check_done:
            alive = [p for p in self.people if p.isAlive]
            if len(alive) >= 2:
                self.appoint_king(tick_num)
                self._king_check_done = True
            return

        if self.king is None:
            # Interregnum: council already formed, waiting to elect
            if self.council:
                # Remove dead council members
                self.council = [p for p in self.council if p.isAlive]
                if self.council:
                    elect_new_king(self, tick_num)
                else:
                    # Everyone on council is dead — pick from survivors
                    form_council(self)
                    if self.council:
                        elect_new_king(self, tick_num)
            else:
                # No council yet — form one if enough survivors
                alive = [p for p in self.people if p.isAlive]
                if len(alive) >= 1:
                    form_council(self)
            return

        # ── Check if king is still alive ──────────────────────────────────
        if not self.king.person.isAlive:
            self.succession_log.append((tick_num, self.king.person.name, 'died'))
            self.king = None
            form_council(self)
            if self.council:
                elect_new_king(self, tick_num)
            return

        # ── Check for overthrow ───────────────────────────────────────────
        if self.king.check_overthrow(self):
            self.succession_log.append((tick_num, self.king.person.name, 'overthrown'))
            # Make outcast
            old         = self.king.person
            old.symbol  = 'O'          # 'O' for outcast
            old.is_king = False
            old.is_outcast = True
            self.king   = None
            self.starvation_count = 0
            form_council(self)
            if self.council:
                elect_new_king(self, tick_num)
            return

        # ── Normal reign tick ─────────────────────────────────────────────
        update_loyalties(self)
        self.king.tick(self, tick_num)

    # ── Display ──────────────────────────────────────────────────────────────
    def display(self):
        for row in self.grid:
            print(" ".join(
                tile.civilization.symbol if tile.civilization else tile.symbol()
                for tile in row
            ))