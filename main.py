import time
import os
import random
from World import World

def draw_bar(label, value, max_value=100, length=15):
    filled = int((value / max_value) * length)
    bar = '█' * filled + '░' * (length - filled)
    return f"{label}:[{bar}]{value:>3}"

# ── Stat tracking ─────────────────────────────────────────────────────────────
class Stats:
    def __init__(self):
        self.total_born       = 0
        self.births_log       = []   # (tick, child_name, parent_names)
        self.deaths_log       = []   # (tick, name, age, cause)
        self.peak_population  = 0
        self.huts_built       = 0
        self.storehouses_built= 0
        # per-person lifetime stats: name → dict
        self.person_stats     = {}

    def register_person(self, person):
        if person.name not in self.person_stats:
            self.person_stats[person.name] = {
                'wood': 0, 'stone': 0, 'fiber': 0,
                'food': 0, 'meat': 0, 'harvested': 0,
                'births': 0, 'max_age': 0, 'max_intel': 0,
            }

    def snapshot(self, person):
        """Call each tick to update peak intel/age."""
        s = self.person_stats.get(person.name)
        if s is None:
            return
        s['max_age']   = max(s['max_age'],   person.age)
        s['max_intel'] = max(s['max_intel'], person.intelligence)

stats = Stats()

# ── Inventory diff helper ─────────────────────────────────────────────────────
def record_inventory_gains(person, old_inv):
    s = stats.person_stats.get(person.name)
    if s is None:
        return
    new_inv = person.inventory[:]
    for item in new_inv:
        if item in old_inv:
            old_inv.remove(item)
        else:
            if item in s:
                s[item] += 1

def run_person_tick(person, world, tick):
    person.update_hunger(tick)
    person.age_up(tick)
    person.intelligence_gain(tick)
    person.tick_cooldowns()

    if not person.isAlive:
        return

    old_inv = person.inventory[:]

    if person.hunger < 30 and not person.has_edible_food():
        person.hunt(world)
        if person.current_task == 'hunting':
            person.move(world, tick)
    else:
        if person.has_farm:
            person.try_harvest(world)
            if person.current_task != 'harvesting':
                person.try_collect_seed(world)
                person.try_plant(world)
                if not person.seek_partner(world):
                    person.move(world, tick)
        else:
            person.try_collect_seed(world)
            person.try_plant(world)
            if not person.seek_partner(world):
                person.move(world, tick)

    person.try_share_food(world)

    if person.health >= 70 and person.hunger >= 40 and person.birth_cooldown == 0 and person.age >= 15:
        person.try_reproduce(world)

    record_inventory_gains(person, old_inv)
    stats.snapshot(person)

# ── Setup ─────────────────────────────────────────────────────────────────────
world = World(50, 50, population_cap=20)
adam  = world.spawn_person("Adam")
stats.register_person(adam)
stats.total_born += 1

eve = None
for _ in range(1000):
    x = adam.x + random.randint(-5, 5)
    y = adam.y + random.randint(-5, 5)
    if 0 <= x < world.width and 0 <= y < world.height:
        tile = world.grid[y][x]
        if tile.terrain == 'grass' and tile.civilization is None:
            from Civilization import Person
            eve = Person("Eve", x, y)
            world.grid[y][x].civilization = eve
            world.people.append(eve)
            stats.register_person(eve)
            stats.total_born += 1
            break

world.seed_food_near(adam.x, adam.y, radius=8, count=12)

tick          = 0
recent_births = []   # last 5 for live display

# ── Main loop ─────────────────────────────────────────────────────────────────
while any(p.isAlive for p in world.people):
    os.system('cls' if os.name == 'nt' else 'clear')
    tick += 1

    prev_people   = set(id(p) for p in world.people)
    prev_huts     = len(world.huts)
    prev_stores   = len(world.storehouses)
    alive_before  = {p.name for p in world.people if p.isAlive}

    for person in list(world.people):
        if person.isAlive:
            run_person_tick(person, world, tick)

    # ── Detect births ─────────────────────────────────────────────────────────
    for p in world.people:
        if id(p) not in prev_people:
            parents = [x.name for x in world.people if x is not p and x.birth_cooldown > 140]
            entry   = (tick, p.name, parents)
            stats.births_log.append(entry)
            stats.total_born += 1
            recent_births.append(entry)
            if len(recent_births) > 5:
                recent_births.pop(0)
            stats.register_person(p)

    # ── Detect deaths ─────────────────────────────────────────────────────────
    for p in world.people:
        if p.name in alive_before and not p.isAlive:
            cause = 'starvation' if p.hunger <= 0 else 'old age' if p.age >= 80 else 'unknown'
            stats.deaths_log.append((tick, p.name, p.age, cause))
            s = stats.person_stats.get(p.name)
            if s:
                s['max_age'] = p.age

    # ── Detect new buildings ───────────────────────────────────────────────────
    stats.huts_built        += len(world.huts)        - prev_huts
    stats.storehouses_built += len(world.storehouses) - prev_stores

    # World updates
    world.grow_farms()
    world.update_animals(tick)
    if tick % 50 == 0:
        world.respawn_animals()

    world.prune_dead()

    # ── Live display ──────────────────────────────────────────────────────────
    alive_people = [p for p in world.people if p.isAlive]
    pop          = len(alive_people)
    stats.peak_population = max(stats.peak_population, pop)

    print(f"  ╔══════════════════════════════════════════════════════════╗")
    print(f"  ║  TICK: {tick:<6}  |  Population: {pop}/{world.population_cap}  Peak: {stats.peak_population}          ║")
    print(f"  ╠══════════════════════════════════════════════════════════╣")

    for p in alive_people:
        inv_f  = p.inventory_count('food')
        inv_m  = p.inventory_count('meat')
        inv_h  = p.inventory_count('harvested')
        inv_s  = p.inventory_count('seed')
        inv_w  = p.inventory_count('wood')
        inv_st = p.inventory_count('stone')
        inv_fi = p.inventory_count('fiber')
        cd     = f" CD:{p.birth_cooldown}" if p.birth_cooldown > 0 else ""
        print(f"  ║  {p.name:<6} A:{p.age:<3} I:{p.intelligence:<3}{cd:<7}")
        print(f"  ║    {draw_bar('HP', p.health)}  {draw_bar('HG', p.hunger)}")
        print(f"  ║    Task:{p.current_task:<14} Inv[{len(p.inventory)}/25]")
        print(f"  ║    Food: F={inv_f} M={inv_m} H={inv_h} S={inv_s}  |  Res: W={inv_w} St={inv_st} Fi={inv_fi}")
        print(f"  ║    Farm:{'Yes' if p.has_farm else 'No':<4} Full:{'Yes' if p.farm_full else 'No':<4}")
        print(f"  ╠══════════════════════════════════════════════════════════╣")

    if recent_births:
        print(f"  ║  Recent births:")
        for bt, bname, bparents in recent_births[-3:]:
            pstr = ' & '.join(bparents) if bparents else '?'
            print(f"  ║    Tick {bt:<6}: {bname} born  (parents: {pstr})")
        print(f"  ╠══════════════════════════════════════════════════════════╣")

    print(f"  ╚══════════════════════════════════════════════════════════╝")
    print()
    world.display()

    time.sleep(0.2)

# ── End screen ────────────────────────────────────────────────────────────────
os.system('cls' if os.name == 'nt' else 'clear')

all_people = list(stats.person_stats.items())
longest    = max(world.people, key=lambda p: p.age, default=None)

# fix: count from all tracked people, not just alive
total_born = stats.total_born

print(f"""
  ╔══════════════════════════════════════════════════════════════╗
  ║              CIVILISATION HAS ENDED                         ║
  ╠══════════════════════════════════════════════════════════════╣
  ║  Survived:        {tick} ticks
  ║  Total born:      {total_born}
  ║  Peak population: {stats.peak_population}
  ║  Total deaths:    {len(stats.deaths_log)}
  ║  Huts built:      {stats.huts_built}
  ║  Storehouses:     {stats.storehouses_built}""")

if longest:
    print(f"  ║  Longest lived:   {longest.name} (Age {longest.age})")

# ── Per-person summary ────────────────────────────────────────────────────────
print(f"  ╠══════════════════════════════════════════════════════════════╣")
print(f"  ║  PERSON SUMMARIES                                           ║")
print(f"  ╠══════════════════════════════════════════════════════════════╣")
for name, s in stats.person_stats.items():
    total_food = s['food'] + s['harvested'] + s['meat']
    total_res  = s['wood'] + s['stone'] + s['fiber']
    print(f"  ║  {name:<8}  Age:{s['max_age']:<4} Intel:{s['max_intel']:<4}")
    print(f"  ║    Food gathered : food={s['food']} harvested={s['harvested']} meat={s['meat']} (total={total_food})")
    print(f"  ║    Res gathered  : wood={s['wood']} stone={s['stone']} fiber={s['fiber']} (total={total_res})")
    print(f"  ╠══════════════════════════════════════════════════════════════╣")

# ── Full births log ───────────────────────────────────────────────────────────
print(f"  ║  FULL BIRTHS LOG                                            ║")
print(f"  ╠══════════════════════════════════════════════════════════════╣")
for bt, bname, bparents in stats.births_log:
    pstr = ' & '.join(bparents) if bparents else '?'
    print(f"  ║    Tick {bt:<6}: {bname:<8} (parents: {pstr})")

# ── Deaths log ────────────────────────────────────────────────────────────────
if stats.deaths_log:
    print(f"  ╠══════════════════════════════════════════════════════════════╣")
    print(f"  ║  DEATHS LOG                                                 ║")
    print(f"  ╠══════════════════════════════════════════════════════════════╣")
    for dt, dname, dage, cause in stats.deaths_log:
        print(f"  ║    Tick {dt:<6}: {dname:<8} died age {dage:<4} ({cause})")

print(f"  ╚══════════════════════════════════════════════════════════════╝")