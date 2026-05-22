import time
import os
import random
from World import World
from King import TAX_INTERVAL

def draw_bar(label, value, max_value=100, length=15):
    filled = int((value / max_value) * length)
    bar = '█' * filled + '░' * (length - filled)
    return f"{label}:[{bar}]{value:>3}"

def draw_loyalty_bar(value, length=10):
    filled = int((value / 100) * length)
    bar = '█' * filled + '░' * (length - filled)
    return f"[{bar}]{value:>3}"

# ── Stat tracking ─────────────────────────────────────────────────────────────
class Stats:
    def __init__(self):
        self.total_born        = 0
        self.births_log        = []
        self.deaths_log        = []
        self.peak_population   = 0
        self.huts_built        = 0
        self.storehouses_built = 0
        self.person_stats      = {}

    def register_person(self, person):
        if person.name not in self.person_stats:
            self.person_stats[person.name] = {
                'wood': 0, 'stone': 0, 'fiber': 0,
                'food': 0, 'meat': 0, 'harvested': 0,
                'births': 0, 'max_age': 0, 'max_intel': 0,
                'born_tick': 0, 'death_tick': None,
                'learning_rate': person.learning_rate,
            }

    def snapshot(self, person):
        s = self.person_stats.get(person.name)
        if s is None:
            return
        s['max_age']   = max(s['max_age'],   person.age)
        s['max_intel'] = max(s['max_intel'], person.intelligence)

    def record_inventory_gains(self, person, old_inv):
        s = self.person_stats.get(person.name)
        if s is None:
            return
        new_inv = person.inventory[:]
        for item in new_inv:
            if item in old_inv:
                old_inv.remove(item)
            else:
                if item in s:
                    s[item] += 1

stats = Stats()

# ── Setup ─────────────────────────────────────────────────────────────────────
world = World(50, 50, population_cap=10)
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
recent_births = []

# ── Main loop ─────────────────────────────────────────────────────────────────
while any(p.isAlive for p in world.people):
    os.system('cls' if os.name == 'nt' else 'clear')
    tick += 1

    prev_people  = set(id(p) for p in world.people)
    prev_huts    = len(world.huts)
    prev_stores  = len(world.storehouses)
    alive_before = {p.name for p in world.people if p.isAlive}

    for person in list(world.people):
        if person.isAlive:
            old_inv = person.tick(world, tick)
            stats.record_inventory_gains(person, old_inv)
            stats.snapshot(person)

    # ── King governance update ────────────────────────────────────────────
    world.update_king(tick)

    # ── Detect births ─────────────────────────────────────────────────────
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
            s = stats.person_stats.get(p.name)
            if s:
                s['born_tick'] = tick

    # ── Detect deaths ─────────────────────────────────────────────────────
    for p in world.people:
        if p.name in alive_before and not p.isAlive:
            cause = 'starvation' if p.hunger <= 0 else 'old age' if p.age >= 80 else 'unknown'
            stats.deaths_log.append((tick, p.name, p.age, cause))
            s = stats.person_stats.get(p.name)
            if s:
                s['max_age']   = p.age
                s['death_tick'] = tick

    # ── Detect new buildings ──────────────────────────────────────────────
    stats.huts_built        += len(world.huts)        - prev_huts
    stats.storehouses_built += len(world.storehouses) - prev_stores

    # World updates
    world.grow_farms()
    world.update_regrowth()
    world.update_animals(tick)
    if tick % 50 == 0:
        world.respawn_animals()
    world.apply_hut_healing()
    world.recompute_population_cap()
    world.prune_dead()

    # ── Live display ──────────────────────────────────────────────────────
    alive_people  = [p for p in world.people if p.isAlive]
    pop           = len(alive_people)
    stats.peak_population = max(stats.peak_population, pop)

    hut_bonus   = world._hut_pop_bonus
    food_bonus  = world.storehouse_food_bonus()
    stored_food = world.total_stored_food()

    # ── King panel ────────────────────────────────────────────────────────
    print(f"  ╔══════════════════════════════════════════════════════════╗")
    print(f"  ║  TICK: {tick:<6}  |  Pop: {pop}/{world.population_cap}  Peak: {stats.peak_population:<5}          ║")
    print(f"  ║  Cap: base={world._base_pop_cap} + huts={hut_bonus} + food={food_bonus} (stored:{stored_food:<4})         ║")
    print(f"  ╠══════════════════════════════════════════════════════════╣")

    if world.king is not None:
        k  = world.king
        kp = k.person
        rebel_count  = sum(1 for p in alive_people if getattr(p, 'is_rebel', False))
        loyal_count  = sum(1 for p in alive_people
                          if not getattr(p, 'is_rebel', False) and p is not kp)
        avg_loyalty  = (sum(getattr(p, 'loyalty', 50) for p in alive_people if p is not kp)
                        / max(1, len(alive_people) - 1))
        mod_str = (f"+{k.coronation_modifier}" if k.coronation_modifier > 0
                   else str(k.coronation_modifier) if k.coronation_modifier < 0 else " 0")
        print(f"  ║  👑 KING: {kp.name:<8} I:{kp.intelligence:<3} Age:{kp.age:<3} Reign:{k.reign_ticks} ticks")
        print(f"  ║     Ruler style: {k.style_name:<18} (INT base + roll {mod_str})")
        print(f"  ║     Personality: tax={k.tax_amount} leniency={k.leniency} adapt={k.adapt_speed:.1f} skip@{int(k.starvation_skip*100)}%starv")
        print(f"  ║     Build Zone : radius={k.build_radius} @ ({k.capital_x},{k.capital_y})  eagerness={k.radius_eagerness}")
        print(f"  ║     Tax cycle  : {k.tax_timer}/{TAX_INTERVAL}  Taxed:{k.total_taxed}  Redist:{k.total_redistributed}  Dodged:{k.total_rebel_dodges}")
        print(f"  ║     Starvation : {world.starvation_count}/{max(1,pop)*3} ticks (overthrow threshold)")
        print(f"  ║     Loyalty    : avg={avg_loyalty:>4.0f}  Loyal={loyal_count}  Rebels={rebel_count}")
        print(f"  ╠══════════════════════════════════════════════════════════╣")
    elif world.council:
        print(f"  ║  ⚖  INTERREGNUM — Council of {len(world.council)}:")
        for cp in world.council:
            print(f"  ║     {cp.name:<8} I:{cp.intelligence:<3}  Food:{cp.total_food_count()}")
        print(f"  ╠══════════════════════════════════════════════════════════╣")
    else:
        print(f"  ║  (No ruler yet)                                          ║")
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
        gc     = f" GC:{p.gather_cooldown}" if p.gather_cooldown > 0 else ""

        # Status badges
        badge = ''
        if getattr(p, 'is_king', False):
            badge = ' 👑'
        elif getattr(p, 'is_outcast', False):
            badge = ' 🚫'
        elif getattr(p, 'is_rebel', False):
            badge = ' ⚡'

        loyalty_str = ''
        if world.king is not None and p is not world.king.person:
            loyalty_str = f"  Loy:{draw_loyalty_bar(getattr(p, 'loyalty', 50))}"

        print(f"  ║  {p.name:<6} A:{p.age:<3} I:{p.intelligence:<3} LR:{p.learning_rate}{badge}{cd:<7}{gc}")
        print(f"  ║    {draw_bar('HP', p.health)}  {draw_bar('HG', p.hunger)}")
        print(f"  ║    Task:{p.current_task:<18} Inv[{len(p.inventory)}/25]{loyalty_str}")
        print(f"  ║    Food: F={inv_f} M={inv_m} H={inv_h} S={inv_s}  |  Res: W={inv_w} St={inv_st} Fi={inv_fi}")
        print(f"  ║    Farm:{'Yes' if p.has_farm else 'No':<4} Full:{'Yes' if p.farm_full else 'No':<4}")
        print(f"  ╠══════════════════════════════════════════════════════════╣")

    if recent_births:
        print(f"  ║  Recent births:")
        for bt, bname, bparents in recent_births[-3:]:
            pstr = ' & '.join(bparents) if bparents else '?'
            print(f"  ║    Tick {bt:<6}: {bname} born  (parents: {pstr})")
        print(f"  ╠══════════════════════════════════════════════════════════╣")

    # ── Succession log (last 4 events) ────────────────────────────────────
    if world.succession_log:
        print(f"  ║  Succession log (recent):")
        for st, sname, sreason in world.succession_log[-4:]:
            icon = {'crowned': '👑', 'died': '💀', 'overthrown': '⚡', 'elected': '🗳'}.get(sreason, '?')
            print(f"  ║    Tick {st:<6}: {sname:<8} — {icon} {sreason}")
        print(f"  ╠══════════════════════════════════════════════════════════╣")

    print(f"  ╚══════════════════════════════════════════════════════════╝")
    print()
    world.display()

    time.sleep(0.2)

# ── End screen ────────────────────────────────────────────────────────────────
os.system('cls' if os.name == 'nt' else 'clear')

longest    = max(world.people, key=lambda p: p.age, default=None)
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
  ║  Storehouses:     {stats.storehouses_built}
  ║  Total rulers:    {len(world.succession_log)}""")

if longest:
    print(f"  ║  Longest lived:   {longest.name} (Age {longest.age})")

# ── Succession history ────────────────────────────────────────────────────────
if world.succession_log:
    print(f"  ╠══════════════════════════════════════════════════════════════╣")
    print(f"  ║  SUCCESSION HISTORY                                         ║")
    print(f"  ╠══════════════════════════════════════════════════════════════╣")
    for st, sname, sreason in world.succession_log:
        icon = {'crowned': '👑', 'died': '💀', 'overthrown': '⚡', 'elected': '🗳'}.get(sreason, '?')
        # Find style if king object still around
        style_str = ''
        if world.king and world.king.person.name == sname:
            style_str = f"  [{world.king.style_name}]"
        print(f"  ║    Tick {st:<6}: {sname:<8} — {icon} {sreason}{style_str}")

print(f"  ╠══════════════════════════════════════════════════════════════╣")
print(f"  ║  PERSON SUMMARIES                                           ║")
print(f"  ╠══════════════════════════════════════════════════════════════╣")
for name, s in stats.person_stats.items():
    total_food = s['food'] + s['harvested'] + s['meat']
    total_res  = s['wood'] + s['stone'] + s['fiber']
    born_str  = f"tick {s['born_tick']}" if s['born_tick'] else "start"
    death_str = f"tick {s['death_tick']}" if s['death_tick'] else "survived"
    lifespan  = (s['death_tick'] or tick) - s['born_tick']
    print(f"  ║  {name:<8}  Born:{born_str:<10} Died:{death_str:<12} Lifespan:{lifespan} ticks")
    print(f"  ║    Age at death:{s['max_age']:<4}  Intel at death:{s['max_intel']:<4}  LearningRate:{s['learning_rate']}")
    print(f"  ║    Food gathered : food={s['food']} harvested={s['harvested']} meat={s['meat']} (total={total_food})")
    print(f"  ║    Res gathered  : wood={s['wood']} stone={s['stone']} fiber={s['fiber']} (total={total_res})")
    print(f"  ╠══════════════════════════════════════════════════════════╣")

print(f"  ║  FULL BIRTHS LOG                                            ║")
print(f"  ╠══════════════════════════════════════════════════════════════╣")
for bt, bname, bparents in stats.births_log:
    pstr = ' & '.join(bparents) if bparents else '?'
    print(f"  ║    Tick {bt:<6}: {bname:<8} (parents: {pstr})")

if stats.deaths_log:
    print(f"  ╠══════════════════════════════════════════════════════════╣")
    print(f"  ║  DEATHS LOG                                                 ║")
    print(f"  ╠══════════════════════════════════════════════════════════╣")
    for dt, dname, dage, cause in stats.deaths_log:
        print(f"  ║    Tick {dt:<6}: {dname:<8} died age {dage:<4} ({cause})")

print(f"  ╚══════════════════════════════════════════════════════════════╝")