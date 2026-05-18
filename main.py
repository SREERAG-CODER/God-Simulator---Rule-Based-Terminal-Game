import time
import os
import random
from World import World

def draw_bar(label, value, max_value=100, length=15):
    filled = int((value / max_value) * length)
    bar = '█' * filled + '░' * (length - filled)
    return f"{label}:[{bar}]{value:>3}"

def run_person_tick(person, world, tick):
    """Run one tick of AI logic for a single person."""
    person.update_hunger(tick)
    person.age_up(tick)
    person.intelligence_gain(tick)
    person.tick_cooldowns()

    if not person.isAlive:
        return

    # Priority decision tree
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

    # Share food with starving neighbours before thinking about reproduction
    person.try_share_food(world)

    # Attempt reproduction (only if well-fed and healthy)
    if person.health >= 70 and person.hunger >= 40 and person.birth_cooldown == 0 and person.age >= 15:
        person.try_reproduce(world)

# ── Setup ────────────────────────────────────────────────────────────────────
world = World(50, 50, population_cap=20)
adam = world.spawn_person("Adam")

# Spawn Eve within 5 tiles of Adam
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
            break

# Guarantee food density around the spawn area — no starter pack, just a fair world
world.seed_food_near(adam.x, adam.y, radius=8, count=12)

tick = 0
births = []          # log: (tick, child_name, parent_names)  — last 5 shown

# ── Main loop ────────────────────────────────────────────────────────────────
while any(p.isAlive for p in world.people):
    os.system('cls' if os.name == 'nt' else 'clear')
    tick += 1

    prev_people = set(id(p) for p in world.people)

    # Tick every living person
    for person in list(world.people):   # copy — list may grow mid-tick (births)
        if person.isAlive:
            run_person_tick(person, world, tick)

    # Detect new births this tick
    for p in world.people:
        if id(p) not in prev_people:
            parents = [x.name for x in world.people if x is not p and x.birth_cooldown > 140]
            births.append((tick, p.name, parents))
            if len(births) > 5:
                births.pop(0)

    # World updates
    world.grow_farms()
    world.update_animals(tick)
    if tick % 50 == 0:
        world.respawn_animals()

    world.prune_dead()

    # ── Display ──────────────────────────────────────────────────────────────
    alive_people = [p for p in world.people if p.isAlive]
    pop = len(alive_people)

    print(f"  ╔══════════════════════════════════════════════════════════╗")
    print(f"  ║  TICK: {tick:<6}  |  Population: {pop}/{world.population_cap}                     ║")
    print(f"  ╠══════════════════════════════════════════════════════════╣")

    for p in alive_people:
        inv_f = p.inventory_count('food')
        inv_m = p.inventory_count('meat')
        inv_h = p.inventory_count('harvested')
        inv_s = p.inventory_count('seed')
        cd    = f" CD:{p.birth_cooldown}" if p.birth_cooldown > 0 else ""
        print(f"  ║  {p.name:<6} A:{p.age:<3} I:{p.intelligence:<3}{cd:<7}")
        print(f"  ║    {draw_bar('HP', p.health)}  {draw_bar('HG', p.hunger)}")
        print(f"  ║    Task:{p.current_task:<12} Inv[{len(p.inventory)}/25] F={inv_f} M={inv_m} H={inv_h} S={inv_s}")
        print(f"  ║    Farm:{'Yes' if p.has_farm else 'No':<4} Full:{'Yes' if p.farm_full else 'No':<4}")
        print(f"  ╠══════════════════════════════════════════════════════════╣")

    if births:
        print(f"  ║  Recent births:")
        for bt, bname, bparents in births[-3:]:
            pstr = ' & '.join(bparents) if bparents else '?'
            print(f"  ║    Tick {bt:<6}: {bname} born  (parents: {pstr})")
        print(f"  ╠══════════════════════════════════════════════════════════╣")

    print(f"  ╚══════════════════════════════════════════════════════════╝")
    print()
    world.display()

    time.sleep(0.2)

# ── End screen ───────────────────────────────────────────────────────────────
os.system('cls' if os.name == 'nt' else 'clear')
longest = max(world.people, key=lambda p: p.age) if world.people else None
print(f"""
  ╔══════════════════════════════════════════════════╗
  ║           CIVILISATION HAS ENDED                ║
  ║                                                  ║
  ║   Survived:   {tick} ticks                          ║
  ║   Total born: {len(world.people)}                               ║
  ║   Longest lived: {longest.name if longest else '—'} (Age {longest.age if longest else 0})           ║
  ║                                                  ║
  ║   Births log:                                    ║""")
for bt, bname, bparents in births:
    pstr = ' & '.join(bparents) if bparents else '?'
    print(f"  ║     Tick {bt:<6}: {bname:<8} ({pstr})")
print(f"""  ╚══════════════════════════════════════════════════╝
""")