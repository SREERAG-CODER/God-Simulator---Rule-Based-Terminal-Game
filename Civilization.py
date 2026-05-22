import random
from collections import deque

CHILD_NAMES = [
    "Cain", "Abel", "Seth", "Aya", "Lila", "Ren", "Kael", "Mira",
    "Theo", "Nora", "Eli", "Zara", "Ivan", "Sena", "Oryn", "Deva",
    "Luna", "Rex", "Vera", "Otto", "Iris", "Hugo", "Rosa", "Leo",
    "Finn", "Maya", "Axel", "Sia", "Bram", "Lyra", "Cole", "Wren",
]

# Intelligence thresholds
INT_BUILD_HUT        = 80
INT_BUILD_STOREHOUSE = 100

# ── Reproduction thresholds (lowered for playability) ─────────────────────────
REPRO_MIN_INTELLIGENCE = 10   # matches starting intelligence
REPRO_MIN_AGE          = 15   # age increments every 40 ticks, so ~600 ticks to reach
REPRO_MIN_HEALTH       = 60   # was 70
REPRO_MIN_HUNGER       = 35   # was 40

# How often a new build site may be proposed (world ticks between attempts)
BUILD_COOLDOWN_TICKS = 200


class Person:
    def __init__(self, name, x, y, intelligence=10, learning_rate=None):
        self.name          = name
        self.x             = x
        self.y             = y
        self.age           = 0
        self.health        = 100
        self.hunger        = 100
        self.intelligence  = intelligence
        self.symbol        = 'P'
        self.isAlive       = True
        self.inventory     = []
        self.max_inventory = 25
        self.has_farm      = False
        self.farm_x        = None
        self.farm_y        = None
        self.farm_full     = False
        self.current_task  = 'roaming'
        self.birth_cooldown = 0

        # Building state
        self.build_target  = None

        # Strategic gathering state
        self.gather_cooldown   = 0
        self.gather_target     = None

        # Intelligence personality trait
        self.learning_rate = learning_rate if learning_rate is not None else random.randint(1, 8)

        # XP accumulator
        self._xp_pool = 0.0

        # ── King / governance fields ──────────────────────────────────────
        self.is_king    = False
        self.is_outcast = False
        self.loyalty    = 50          # 0–100; below 25 = rebel
        self.is_rebel   = False

        # ── Tracking fields (for end-screen stats) ────────────────────────
        self.total_children  = 0      # incremented when this person reproduces
        self.total_kills     = 0      # animals hunted
        self.ticks_alive     = 0      # incremented each tick while alive
        self.cause_of_death  = None   # set when person dies

    # ════════════════════════════════════════════════════════════
    # Inventory helpers
    # ════════════════════════════════════════════════════════════
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
        return self.has_item('food') or self.has_item('harvested') or self.has_item('meat')

    def total_food_count(self):
        return (self.inventory_count('food') +
                self.inventory_count('harvested') +
                self.inventory_count('meat'))

    # ════════════════════════════════════════════════════════════
    # Eating
    # ════════════════════════════════════════════════════════════
    def try_eat(self):
        # Eat proactively when hunger drops below 70 (not just 50)
        # so people top up food before becoming dangerously hungry
        if self.hunger > 70 and self.health >= 80:
            return
        for item_type, hunger_gain, health_gain in [
            ('meat',      60, 15),
            ('harvested', 40, 10),
            ('food',      30, 8),
        ]:
            if self.has_item(item_type):
                self.remove_item(item_type)
                self.hunger = min(100, self.hunger + hunger_gain)
                self.health = min(100, self.health + health_gain)
                return

    # ════════════════════════════════════════════════════════════
    # Hunger / health / aging
    # ════════════════════════════════════════════════════════════
    def update_hunger(self, tick):
        self.ticks_alive += 1
        # Hunger drops 2 every 10 ticks → 100 ticks to lose 20 hunger
        # Full starvation (100→0) takes ~500 ticks, giving time to find food
        if tick % 10 == 0:
            self.hunger -= 2
        # Only lose health when critically starving (hunger=0)
        # and only 2 HP per tick, so ~50 more ticks to die after hunger hits 0
        if self.hunger <= 0:
            self.hunger = 0
            if tick % 5 == 0:
                self.health -= 2
        if self.health <= 0:
            self.isAlive = False
            if self.cause_of_death is None:
                self.cause_of_death = 'starvation'
            return
        self.try_eat()

    def age_up(self, tick):
        if tick % 40 == 0:
            self.age += 1
            # Old age death: chance increases past age 70
            if self.age >= 70:
                death_chance = (self.age - 70) * 0.05
                if random.random() < death_chance:
                    self.isAlive = False
                    self.cause_of_death = 'old age'

    def _gain_xp(self, amount):
        if self.intelligence >= 200:
            return
        self._xp_pool += amount
        gained = int(self._xp_pool)
        if gained > 0:
            self._xp_pool -= gained
            self.intelligence = min(200, self.intelligence + gained)

    def intelligence_gain(self, tick):
        if tick % 30 == 0:
            self._gain_xp(self.learning_rate * 0.5)

    def tick_cooldowns(self):
        if self.birth_cooldown > 0:
            self.birth_cooldown -= 1
        if self.gather_cooldown > 0:
            self.gather_cooldown -= 1

    # ════════════════════════════════════════════════════════════
    # BFS pathfinder
    # ════════════════════════════════════════════════════════════
    def _find_path_step(self, world, target_x, target_y):
        if self.x == target_x and self.y == target_y:
            return None

        queue   = deque()
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
                tile      = world.grid[ny][nx]
                at_target = (nx == target_x and ny == target_y)
                passable  = (
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

    # ════════════════════════════════════════════════════════════
    # Resource gathering  (wood / stone / fiber)
    # ════════════════════════════════════════════════════════════
    def _gather_resource(self, world, terrain_type, item_name, spent_terrain, radius=12):
        best_dist = radius + 1
        best_pos  = None

        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                tx, ty = self.x + dx, self.y + dy
                if not (0 <= tx < world.width and 0 <= ty < world.height):
                    continue
                if world.grid[ty][tx].terrain == terrain_type:
                    d = abs(dx) + abs(dy)
                    if d < best_dist:
                        best_dist = d
                        best_pos  = (tx, ty)

        if best_pos is None:
            return False

        tx, ty = best_pos

        if abs(self.x - tx) <= 1 and abs(self.y - ty) <= 1 and (self.x != tx or self.y != ty):
            world.grid[ty][tx].terrain = spent_terrain
            self.add_to_inventory(item_name)
            return True

        step = self._find_path_step(world, tx, ty)
        if step:
            ox, oy  = step
            new_x   = self.x + ox
            new_y   = self.y + oy
            next_t  = world.grid[new_y][new_x]
            if next_t.terrain not in ('water',) and next_t.civilization is None:
                world.grid[self.y][self.x].civilization = None
                self.x, self.y = new_x, new_y
                world.grid[self.y][self.x].civilization = self
                return True
        return False

    def gather_wood(self, world):
        self.current_task = 'gathering_wood'
        return self._gather_resource(world, 'forest', 'wood', 'stump')

    def gather_stone(self, world):
        self.current_task = 'gathering_stone'
        return self._gather_resource(world, 'rock', 'stone', 'rubble')

    def gather_fiber(self, world):
        self.current_task = 'gathering_fiber'
        return self._gather_resource(world, 'fiber', 'fiber', 'fiber_spent')

    # ════════════════════════════════════════════════════════════
    # Strategic resource gathering
    # ════════════════════════════════════════════════════════════
    def _world_resource_counts(self, world):
        totals = {'wood': 0, 'stone': 0, 'fiber': 0}
        for p in world.people:
            if p.isAlive:
                for r in totals:
                    totals[r] += p.inventory_count(r)
        return totals

    def _resource_target_amounts(self, world):
        pop = max(1, len(world.people))
        return {
            'wood':  max(8,  pop * 2),
            'stone': max(4,  pop),
            'fiber': max(6,  pop),
        }

    def try_strategic_gather(self, world):
        if self.gather_cooldown > 0:
            return False
        if self.hunger < 60 or self.health < 60:
            return False
        res_carried = (self.inventory_count('wood') +
                       self.inventory_count('stone') +
                       self.inventory_count('fiber'))
        if res_carried >= 4:
            self.gather_cooldown = 20
            return False

        have   = self._world_resource_counts(world)
        target = self._resource_target_amounts(world)

        priority = []
        if self.intelligence >= 55 and have['wood']  < target['wood']:
            priority.append(('wood',  target['wood']  - have['wood']))
        if self.intelligence >= 70 and have['stone'] < target['stone']:
            priority.append(('stone', target['stone'] - have['stone']))
        if self.intelligence >= 40 and have['fiber'] < target['fiber']:
            priority.append(('fiber', target['fiber'] - have['fiber']))

        if not priority:
            return False

        priority.sort(key=lambda x: -x[1])
        resource = priority[0][0]

        terrain_map = {
            'wood':  ('forest', 'stump'),
            'stone': ('rock',   'rubble'),
            'fiber': ('fiber',  'fiber_spent'),
        }
        terrain_type, spent = terrain_map[resource]
        gathered = self._gather_resource(world, terrain_type, resource, spent)
        if gathered:
            self.current_task     = f'stockpiling_{resource}'
            self.gather_cooldown  = 10
            return True

        self.gather_cooldown = 40
        return False

    # ════════════════════════════════════════════════════════════
    # Building logic
    # ════════════════════════════════════════════════════════════
    def _has_materials_for(self, recipe):
        for resource, amount in recipe.items():
            if amount > 0 and self.has_item(resource):
                return True
        return False

    def _gather_for_recipe(self, world, recipe):
        if recipe.get('wood', 0) > 0 and not self.has_item('wood'):
            return self.gather_wood(world)
        if recipe.get('stone', 0) > 0 and not self.has_item('stone'):
            return self.gather_stone(world)
        if recipe.get('fiber', 0) > 0 and not self.has_item('fiber'):
            return self.gather_fiber(world)
        return False

    def _propose_build_site_in_zone(self, world, kind):
        from Building import BuildSite
        MIN_DIST = 8

        king = world.king

        for _ in range(200):
            x = random.randint(1, world.width - 2)
            y = random.randint(1, world.height - 2)

            if king is not None and not self.is_rebel:
                if not king.in_build_zone(x, y):
                    continue

            tile = world.grid[y][x]
            if tile.terrain != 'grass' or tile.civilization is not None:
                continue
            too_close = False
            for blist in (world.huts, world.storehouses, world.build_sites):
                for b in blist:
                    if abs(b.x - x) + abs(b.y - y) < MIN_DIST:
                        too_close = True
                        break
                if too_close:
                    break
            if not too_close:
                return world.add_build_site(kind, x, y)
        return None

    def propose_build_site(self, world, kind):
        return self._propose_build_site_in_zone(world, kind)

    def try_contribute_to_build(self, world):
        from Building import BuildSite

        can_hut        = self.intelligence >= INT_BUILD_HUT
        can_storehouse = (self.intelligence >= INT_BUILD_STOREHOUSE and
                          len(world.huts) > 0)

        if not can_hut:
            return False

        target_site = None
        target_dist = 9999

        for site in world.build_sites:
            if site.kind == 'storehouse' and not can_storehouse:
                continue
            if world.king is not None and not self.is_rebel:
                if not world.king.in_build_zone(site.x, site.y):
                    continue
            d = abs(site.x - self.x) + abs(site.y - self.y)
            if d < target_dist:
                target_dist = d
                target_site = site

        if target_site is None:
            if can_storehouse and not any(s.kind == 'storehouse' for s in world.build_sites):
                if len(world.storehouses) < max(1, len(world.people) // 8):
                    target_site = self._propose_build_site_in_zone(world, 'storehouse')
            if target_site is None and can_hut:
                if len(world.huts) < max(1, len(world.people) // 5):
                    if not any(s.kind == 'hut' for s in world.build_sites):
                        target_site = self._propose_build_site_in_zone(world, 'hut')

        if target_site is None:
            return False

        self.build_target = target_site
        recipe_needed     = target_site.needed

        dist = abs(self.x - target_site.x) + abs(self.y - target_site.y)
        if dist <= 1 and self._has_materials_for(recipe_needed):
            self.current_task = 'building'
            contributed = target_site.contribute(self)
            if contributed:
                self._gain_xp(1.5 + self.learning_rate * 0.2)
            if target_site.is_complete():
                self._gain_xp(3.0)
                world.complete_build_site(target_site)
                self.build_target = None
            return contributed

        still_needed = {k: v for k, v in recipe_needed.items() if v > 0}
        if self._has_materials_for(still_needed):
            self.current_task = 'building'
            step = self._find_path_step(world, target_site.x, target_site.y)
            if step:
                ox, oy = step
                nx, ny = self.x + ox, self.y + oy
                tile   = world.grid[ny][nx]
                if tile.terrain != 'water' and tile.civilization is None:
                    world.grid[self.y][self.x].civilization = None
                    self.x, self.y = nx, ny
                    world.grid[self.y][self.x].civilization = self
                    return True
        else:
            return self._gather_for_recipe(world, still_needed)

        return False

    # ════════════════════════════════════════════════════════════
    # Hut healing
    # ════════════════════════════════════════════════════════════
    def try_seek_hut(self, world):
        from Building import Hut
        if self.health >= 60 or not world.huts:
            return False

        hut = world.nearest_hut(self.x, self.y)
        if hut is None:
            return False

        dist = abs(self.x - hut.x) + abs(self.y - hut.y)
        if dist <= Hut.HEAL_RADIUS:
            self.current_task = 'healing'
            return True

        self.current_task = 'seeking_hut'
        step = self._find_path_step(world, hut.x, hut.y)
        if step:
            ox, oy = step
            nx, ny = self.x + ox, self.y + oy
            tile   = world.grid[ny][nx]
            if tile.terrain != 'water' and tile.civilization is None:
                world.grid[self.y][self.x].civilization = None
                self.x, self.y = nx, ny
                world.grid[self.y][self.x].civilization = self
                return True
        return False

    # ════════════════════════════════════════════════════════════
    # Storehouse interactions
    # ════════════════════════════════════════════════════════════
    def try_deposit_to_storehouse(self, world):
        from Building import Storehouse
        if not world.storehouses:
            return False
        if self.total_food_count() <= 10:
            return False

        sh = world.nearest_storehouse(self.x, self.y)
        if sh is None:
            return False

        dist = abs(self.x - sh.x) + abs(self.y - sh.y)
        if dist <= Storehouse.INTERACT_RADIUS:
            deposited = sh.deposit(self)
            if deposited:
                self.current_task = 'depositing'
            return deposited > 0

        self.current_task = 'depositing'
        step = self._find_path_step(world, sh.x, sh.y)
        if step:
            ox, oy = step
            nx, ny = self.x + ox, self.y + oy
            tile   = world.grid[ny][nx]
            if tile.terrain != 'water' and tile.civilization is None:
                world.grid[self.y][self.x].civilization = None
                self.x, self.y = nx, ny
                world.grid[self.y][self.x].civilization = self
                return True
        return False

    def try_withdraw_from_storehouse(self, world):
        from Building import Storehouse
        if not world.storehouses:
            return False
        if self.hunger > 30 or self.has_edible_food():
            return False

        sh = world.nearest_storehouse(self.x, self.y)
        if sh is None or sh.is_empty():
            return False

        dist = abs(self.x - sh.x) + abs(self.y - sh.y)
        if dist <= Storehouse.INTERACT_RADIUS:
            withdrawn = sh.withdraw(self)
            if withdrawn:
                self.current_task = 'withdrawing'
            return withdrawn > 0

        self.current_task = 'withdrawing'
        step = self._find_path_step(world, sh.x, sh.y)
        if step:
            ox, oy = step
            nx, ny = self.x + ox, self.y + oy
            tile   = world.grid[ny][nx]
            if tile.terrain != 'water' and tile.civilization is None:
                world.grid[self.y][self.x].civilization = None
                self.x, self.y = nx, ny
                world.grid[self.y][self.x].civilization = self
                return True
        return False

    # ════════════════════════════════════════════════════════════
    # Hunting
    # ════════════════════════════════════════════════════════════
    def hunt(self, world):
        if not self.isAlive or self.intelligence < 10:
            return

        self.current_task = 'hunting'
        radius = 9 if self.intelligence >= 60 else 6

        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                tx = self.x + dx
                ty = self.y + dy
                if not (0 <= tx < world.width and 0 <= ty < world.height):
                    continue
                tile = world.grid[ty][tx]
                if tile.civilization is None or tile.civilization.symbol != 'A':
                    continue
                animal = tile.civilization

                if abs(self.x - tx) <= 1 and abs(self.y - ty) <= 1 and (self.x != tx or self.y != ty):
                    animal.isAlive = False
                    world.grid[ty][tx].civilization = None
                    world.animals.remove(animal)
                    self.add_to_inventory('meat')
                    self.total_kills += 1
                    self._gain_xp(1.0 + self.learning_rate * 0.15)
                    self.current_task = 'roaming'
                    return

                step = self._find_path_step(world, tx, ty)
                if step:
                    ox, oy = step
                    nx, ny = self.x + ox, self.y + oy
                    if nx == tx and ny == ty:
                        animal.isAlive = False
                        world.grid[ty][tx].civilization = None
                        world.animals.remove(animal)
                        self.add_to_inventory('meat')
                        self.total_kills += 1
                        self._gain_xp(1.0 + self.learning_rate * 0.15)
                        self.current_task = 'roaming'
                        return
                    next_t = world.grid[ny][nx]
                    if next_t.terrain == 'grass' and next_t.civilization is None:
                        world.grid[self.y][self.x].civilization = None
                        self.x, self.y = nx, ny
                        world.grid[self.y][self.x].civilization = self
                        return

    # ════════════════════════════════════════════════════════════
    # Seed / farming
    # ════════════════════════════════════════════════════════════
    def try_collect_seed(self, world):
        if self.farm_full:
            return
        tile = world.grid[self.y][self.x]
        if tile.terrain == 'seed':
            if self.add_to_inventory('seed'):
                tile.terrain = 'grass'

    def try_plant(self, world):
        if not self.has_item('seed') or self.intelligence < 20:
            return
        if not self.has_farm:
            self.has_farm = True
            self.farm_x   = self.x
            self.farm_y   = self.y
        for dy in range(-5, 6):
            for dx in range(-5, 6):
                px, py = self.farm_x + dx, self.farm_y + dy
                if 0 <= px < world.width and 0 <= py < world.height:
                    if (dx**2 + dy**2) <= 25:
                        tile = world.grid[py][px]
                        if tile.terrain == 'grass' and tile.civilization is None:
                            tile.terrain    = 'farm'
                            tile.grow_timer = 0
                            self.remove_item('seed')
                            self._gain_xp(0.3)
                            self.current_task = 'farming'
                            return
        self.farm_full = True

    def try_harvest(self, world):
        if not self.has_farm:
            return False
        for dy in range(-5, 6):
            for dx in range(-5, 6):
                px, py = self.farm_x + dx, self.farm_y + dy
                if not (0 <= px < world.width and 0 <= py < world.height):
                    continue
                tile = world.grid[py][px]
                if tile.terrain != 'ready':
                    continue
                if self.x == px and self.y == py:
                    tile.terrain    = 'grass'
                    tile.grow_timer = 0
                    self.add_to_inventory('harvested')
                    self.add_to_inventory('seed')
                    self._gain_xp(0.8 + self.learning_rate * 0.1)
                    self.current_task = 'planting'
                    self.farm_full    = False
                    return True
                step = self._find_path_step(world, px, py)
                if step is None:
                    continue
                ox, oy  = step
                nx, ny  = self.x + ox, self.y + oy
                next_t  = world.grid[ny][nx]
                if next_t.terrain in ('grass', 'farm', 'ready') and next_t.civilization is None:
                    world.grid[self.y][self.x].civilization = None
                    self.x, self.y = nx, ny
                    world.grid[self.y][self.x].civilization = self
                    self.current_task = 'harvesting'
                    return True
        return False

    # ════════════════════════════════════════════════════════════
    # Food sharing  (outcasts are skipped as recipients)
    # ════════════════════════════════════════════════════════════
    def try_share_food(self, world):
        if self.hunger <= 50:
            return
        shareable = [i for i in ('harvested', 'food', 'meat') if self.has_item(i)]
        if not shareable:
            return
        neighbours = []
        for other in world.people:
            if other is self or not other.isAlive or other.hunger >= 30:
                continue
            if getattr(other, 'is_outcast', False):
                continue
            if abs(self.x - other.x) + abs(self.y - other.y) <= 1:
                neighbours.append(other)
        if not neighbours:
            return
        neighbours.sort(key=lambda p: p.hunger)
        recipient = neighbours[0]
        for item in ('harvested', 'meat', 'food'):
            if self.has_item(item):
                self.remove_item(item)
                recipient.add_to_inventory(item)
                self.current_task = 'sharing'
                return

    # ════════════════════════════════════════════════════════════
    # Reproduction
    # BUG FIX: lowered thresholds; seek_partner now always runs
    # then try_reproduce is called unconditionally at tick bottom
    # ════════════════════════════════════════════════════════════
    def seek_partner(self, world):
        """Move toward the nearest eligible partner. Returns True if already adjacent."""
        if self.birth_cooldown > 0:
            return False
        if self.health < REPRO_MIN_HEALTH or self.hunger < REPRO_MIN_HUNGER:
            return False
        if self.intelligence < REPRO_MIN_INTELLIGENCE:
            return False
        if self.age < REPRO_MIN_AGE:
            return False
        if len(world.people) >= world.population_cap:
            return False

        best, best_dist = None, float('inf')
        for other in world.people:
            if other is self or not other.isAlive:
                continue
            if other.birth_cooldown > 0:
                continue
            if other.health < REPRO_MIN_HEALTH or other.hunger < REPRO_MIN_HUNGER:
                continue
            if other.intelligence < REPRO_MIN_INTELLIGENCE:
                continue
            if other.age < REPRO_MIN_AGE:
                continue
            dist = abs(self.x - other.x) + abs(self.y - other.y)
            if dist <= 2:
                return True   # already adjacent — try_reproduce will fire below
            if dist < best_dist:
                best_dist = dist
                best      = other

        if best is None:
            return False

        # Move one step toward best partner
        step = self._find_path_step(world, best.x, best.y)
        if step is None:
            return False
        ox, oy = step
        nx, ny = self.x + ox, self.y + oy
        tile   = world.grid[ny][nx]
        if tile.terrain in ('grass', 'food', 'seed') and tile.civilization is None:
            if tile.terrain == 'food':
                self.add_to_inventory('food')
                tile.terrain = 'grass'
            world.grid[self.y][self.x].civilization = None
            self.x, self.y = nx, ny
            world.grid[self.y][self.x].civilization = self
            self.current_task = 'seeking_partner'
            return False   # still moving — not yet adjacent
        return False

    def try_reproduce(self, world):
        """Attempt to produce a child with an adjacent eligible partner."""
        if not self.isAlive or self.birth_cooldown > 0:
            return None
        if self.health < REPRO_MIN_HEALTH or self.hunger < REPRO_MIN_HUNGER:
            return None
        if self.intelligence < REPRO_MIN_INTELLIGENCE:
            return None
        if self.age < REPRO_MIN_AGE:
            return None
        if len(world.people) >= world.population_cap:
            return None

        for other in world.people:
            if other is self or not other.isAlive:
                continue
            if other.birth_cooldown > 0:
                continue
            if other.health < REPRO_MIN_HEALTH or other.hunger < REPRO_MIN_HUNGER:
                continue
            if other.intelligence < REPRO_MIN_INTELLIGENCE:
                continue
            if other.age < REPRO_MIN_AGE:
                continue
            if abs(self.x - other.x) + abs(self.y - other.y) > 2:
                continue

            # Find free tile for child
            child_pos = None
            for dx, dy in random.sample([(0,-1),(0,1),(-1,0),(1,0)], 4):
                cx, cy = self.x + dx, self.y + dy
                if 0 <= cx < world.width and 0 <= cy < world.height:
                    t = world.grid[cy][cx]
                    if t.terrain in ('grass', 'food', 'seed') and t.civilization is None:
                        child_pos = (cx, cy)
                        break
            if child_pos is None:
                continue

            used_names  = {p.name for p in world.people}
            available   = [n for n in CHILD_NAMES if n not in used_names]
            child_name  = available[0] if available else f"Child{len(world.people)}"

            child_intel = int((self.intelligence + other.intelligence) / 2)
            child_intel = max(10, min(200, child_intel + random.randint(-10, 10)))

            child_lr = round((self.learning_rate + other.learning_rate) / 2)
            child_lr = max(1, min(8, child_lr + random.choice([-1, 0, 0, 1])))

            self.birth_cooldown  = 150
            other.birth_cooldown = 150
            self.total_children  += 1

            cx, cy = child_pos
            # Clear food/seed tile if necessary
            if world.grid[cy][cx].terrain in ('food', 'seed'):
                world.grid[cy][cx].terrain = 'grass'

            child  = Person(child_name, cx, cy, intelligence=child_intel, learning_rate=child_lr)
            world.grid[cy][cx].civilization = child
            world.people.append(child)
            return child
        return None

    # ════════════════════════════════════════════════════════════
    # Movement (fallback)
    # ════════════════════════════════════════════════════════════
    def move(self, world, tick):
        if not self.isAlive:
            return False
        self.current_task = 'roaming'
        directions = [(0,-1),(0,1),(-1,0),(1,0)]
        random.shuffle(directions)
        for dx, dy in directions:
            nx, ny = self.x + dx, self.y + dy
            if 0 <= nx < world.width and 0 <= ny < world.height:
                tile = world.grid[ny][nx]
                if tile.terrain in ('grass','food','seed') and tile.civilization is None:
                    if tile.terrain == 'food':
                        self.add_to_inventory('food')
                        tile.terrain = 'grass'
                    elif tile.terrain == 'seed':
                        self.add_to_inventory('seed')
                        tile.terrain = 'grass'
                    world.grid[self.y][self.x].civilization = None
                    self.x, self.y = nx, ny
                    world.grid[self.y][self.x].civilization = self
                    return True
        return False

    # ════════════════════════════════════════════════════════════
    # MAIN TICK
    # BUG FIX: seek_partner no longer gates try_reproduce.
    # try_reproduce is always attempted at the end of the tick
    # when conditions are met.
    # ════════════════════════════════════════════════════════════
    def tick(self, world, tick_num):
        self.update_hunger(tick_num)
        self.age_up(tick_num)
        self.intelligence_gain(tick_num)
        self.tick_cooldowns()

        if not self.isAlive:
            return []

        old_inv = self.inventory[:]

        # ── Survival first: hunt / forage when getting hungry ────────────
        # Trigger at hunger < 50 so they seek food well before starving
        if self.hunger < 50 and not self.has_edible_food():
            if not self.try_withdraw_from_storehouse(world):
                self.hunt(world)
                self.move(world, tick_num)
            self._try_reproduce_end(world)
            return old_inv

        # ── Seek hut if injured ───────────────────────────────────────────
        if self.try_seek_hut(world):
            self._try_reproduce_end(world)
            return old_inv

        # ── Deposit surplus food to storehouse ────────────────────────────
        if self.try_deposit_to_storehouse(world):
            self._try_reproduce_end(world)
            return old_inv

        # ── Building takes priority over farming when smart enough ────────
        if (self.intelligence >= 50 and
                tick_num % 3 == (hash(self.name) % 3)):
            if self.try_contribute_to_build(world):
                self.try_share_food(world)
                self._try_reproduce_end(world)
                return old_inv

        # ── Farming pipeline ──────────────────────────────────────────────
        if self.has_farm:
            self.try_harvest(world)
            if self.current_task != 'harvesting':
                self.try_collect_seed(world)
                self.try_plant(world)
                # Always try to seek partner AND move; seeking partner no longer
                # blocks movement via a guard condition
                self.seek_partner(world)
                if not self.try_strategic_gather(world):
                    self.move(world, tick_num)
        else:
            self.try_collect_seed(world)
            self.try_plant(world)
            self.seek_partner(world)
            if not self.try_strategic_gather(world):
                self.move(world, tick_num)

        # ── Social actions ────────────────────────────────────────────────
        self.try_share_food(world)
        self._try_reproduce_end(world)

        return old_inv

    def _try_reproduce_end(self, world):
        """
        Called at the end of every tick branch.
        Unconditionally attempts reproduction — does NOT depend on seek_partner.
        """
        if (self.health >= REPRO_MIN_HEALTH and
                self.hunger >= REPRO_MIN_HUNGER and
                self.birth_cooldown == 0 and
                self.age >= REPRO_MIN_AGE and
                self.intelligence >= REPRO_MIN_INTELLIGENCE):
            self.try_reproduce(world)