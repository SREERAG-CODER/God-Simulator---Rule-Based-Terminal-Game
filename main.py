import time
import os
import random
from World import World
from King import TAX_INTERVAL

# ─────────────────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────────────────

def bar(label, value, max_value=100, length=15):
    filled = max(0, int((value / max_value) * length))
    b      = '█' * filled + '░' * (length - filled)
    return f"{label}:[{b}]{int(value):>3}"

def loyalty_bar(value, length=10):
    filled = max(0, int((value / 100) * length))
    b      = '█' * filled + '░' * (length - filled)
    return f"[{b}]{int(value):>3}"

W = 62   # box inner width

def box_line(text='', pad=True):
    """Print a single │ ... │ line, truncating or padding to W chars."""
    if pad:
        print(f"  ║  {text:<{W}}║")
    else:
        print(f"  ║{text}║")

def divider():
    print(f"  ╠{'═'*(W+4)}╣")

def top():
    print(f"  ╔{'═'*(W+4)}╗")

def bottom():
    print(f"  ╚{'═'*(W+4)}╝")

def section(title):
    divider()
    box_line(f" ── {title} {'─'*(W - len(title) - 5)}")
    divider()


# ─────────────────────────────────────────────────────────────────────────────
# Stat tracking
# ─────────────────────────────────────────────────────────────────────────────

class Stats:
    def __init__(self):
        self.total_born        = 0
        self.births_log        = []   # (tick, name, [parent_names])
        self.deaths_log        = []   # (tick, name, age, cause, intel)
        self.peak_population   = 0
        self.huts_built        = 0
        self.storehouses_built = 0
        self.food_consumed     = 0    # rough tally via eat calls
        # per-name lineage: name → parent names
        self.parents           = {}
        # generation depth: name → int
        self.generation        = {}

    def register_birth(self, person, parent_names, tick):
        self.total_born += 1
        self.births_log.append((tick, person.name, parent_names))
        self.parents[person.name] = parent_names
        if parent_names:
            parent_gens = [self.generation.get(n, 0) for n in parent_names]
            self.generation[person.name] = max(parent_gens) + 1
        else:
            self.generation[person.name] = 0

    def record_death(self, person, tick):
        cause = person.cause_of_death or 'unknown'
        self.deaths_log.append((tick, person.name, person.age, cause, person.intelligence))


# ─────────────────────────────────────────────────────────────────────────────
# World + initial population
# ─────────────────────────────────────────────────────────────────────────────

# Give Adam & Eve enough starting intelligence to reproduce immediately
STARTING_INTEL = 10

world = World(50, 50, population_cap=10)
stats = Stats()

adam = world.spawn_person("Adam", intelligence=STARTING_INTEL)
stats.register_birth(adam, [], tick=0)

eve = None
for _ in range(1000):
    x = adam.x + random.randint(-5, 5)
    y = adam.y + random.randint(-5, 5)
    if 0 <= x < world.width and 0 <= y < world.height:
        tile = world.grid[y][x]
        if tile.terrain == 'grass' and tile.civilization is None:
            from Civilization import Person
            eve = Person("Eve", x, y, intelligence=STARTING_INTEL)
            world.grid[y][x].civilization = eve
            world.people.append(eve)
            stats.register_birth(eve, [], tick=0)
            break

world.seed_food_near(adam.x, adam.y, radius=10, count=30)

# Give starting characters food so they don't starve before finding any
for _starter in [adam, eve]:
    if _starter:
        for _ in range(6):
            _starter.add_to_inventory('food')

tick          = 0
recent_births = []   # last 5 birth events for live display
recent_deaths = []   # last 5 death events for live display

# Snapshot previous set of people IDs each tick to detect births/deaths
prev_ids = {id(p): p for p in world.people}


# ─────────────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────────────

while any(p.isAlive for p in world.people):
    os.system('cls' if os.name == 'nt' else 'clear')
    tick += 1

    prev_alive_names = {p.name for p in world.people if p.isAlive}
    prev_huts        = len(world.huts)
    prev_stores      = len(world.storehouses)

    # ── Tick all people ───────────────────────────────────────────────────
    for person in list(world.people):
        if person.isAlive:
            person.tick(world, tick)

    # ── King governance ───────────────────────────────────────────────────
    world.update_king(tick)

    # ── Detect births ─────────────────────────────────────────────────────
    for p in world.people:
        if id(p) not in prev_ids:
            parent_names = [x.name for x in world.people
                            if x is not p and x.birth_cooldown > 140]
            entry = (tick, p.name, parent_names)
            stats.register_birth(p, parent_names, tick)
            recent_births.append(entry)
            if len(recent_births) > 5:
                recent_births.pop(0)

    # ── Detect deaths ─────────────────────────────────────────────────────
    for p in world.people:
        if p.name in prev_alive_names and not p.isAlive:
            stats.record_death(p, tick)
            entry = (tick, p.name, p.age, p.cause_of_death or 'unknown')
            recent_deaths.append(entry)
            if len(recent_deaths) > 5:
                recent_deaths.pop(0)
            # If dead king, mark reason
            if getattr(p, 'is_king', False):
                if world.succession_log and world.succession_log[-1][1] == p.name:
                    pass   # already logged by update_king
                else:
                    world.succession_log.append((tick, p.name, 'died'))

    # ── Building tally ────────────────────────────────────────────────────
    stats.huts_built        += len(world.huts)        - prev_huts
    stats.storehouses_built += len(world.storehouses) - prev_stores

    # ── World updates ─────────────────────────────────────────────────────
    world.grow_farms()
    world.update_regrowth()
    world.update_animals(tick)
    if tick % 50 == 0:
        world.respawn_animals()
    world.apply_hut_healing()
    world.recompute_population_cap()
    world.prune_dead()

    # ── Snapshot for next tick ────────────────────────────────────────────
    prev_ids = {id(p): p for p in world.people}

    # ─────────────────────────────────────────────────────────────────────
    # LIVE DISPLAY
    # ─────────────────────────────────────────────────────────────────────
    alive_people = [p for p in world.people if p.isAlive]
    pop          = len(alive_people)
    stats.peak_population = max(stats.peak_population, pop)

    hut_bonus    = world._hut_pop_bonus
    food_bonus   = world.storehouse_food_bonus()
    stored_food  = world.total_stored_food()
    rebel_count  = sum(1 for p in alive_people if getattr(p, 'is_rebel', False))
    king_person  = world.king.person if world.king is not None else None
    loyal_count  = sum(1 for p in alive_people
                       if not getattr(p, 'is_rebel', False)
                       and p is not king_person)

    # ══ Header ═══════════════════════════════════════════════════════════
    top()
    box_line(f" TICK: {tick:<7}  Pop: {pop}/{world.population_cap}   Peak: {stats.peak_population}   "
             f"Born: {stats.total_born}   Deaths: {len(stats.deaths_log)}")
    box_line(f" Cap : base={world._base_pop_cap} + huts={hut_bonus} + food={food_bonus}  "
             f"(stored food: {stored_food})")
    box_line(f" Huts: {len(world.huts)}   Storehouses: {len(world.storehouses)}   "
             f"Build sites active: {len(world.build_sites)}   Animals: {len(world.animals)}")

    # ══ King panel ════════════════════════════════════════════════════════
    section("KING & GOVERNANCE")

    if world.king is not None:
        k  = world.king
        kp = k.person
        avg_loyalty = (sum(getattr(p, 'loyalty', 50) for p in alive_people if p is not kp)
                       / max(1, len(alive_people) - 1))
        mod_str = (f"+{k.coronation_modifier}" if k.coronation_modifier > 0
                   else str(k.coronation_modifier) if k.coronation_modifier < 0 else " 0")

        box_line(f" 👑  {kp.name}   Age:{kp.age}   INT:{kp.intelligence}   "
                 f"LR:{kp.learning_rate}   Reign: {k.reign_ticks} ticks")
        box_line(f"     Style    : {k.style_name}  (INT-base + roll {mod_str})")
        box_line(f"     Traits   : tax={k.tax_amount}  leniency={k.leniency}  "
                 f"adapt={k.adapt_speed:.1f}  skip@{int(k.starvation_skip*100)}% starv")
        box_line(f"     Build    : radius={k.build_radius}  capital=({k.capital_x},{k.capital_y})  "
                 f"eagerness={k.radius_eagerness}")
        box_line(f"     Tax cycle: {k.tax_timer}/{TAX_INTERVAL}   "
                 f"Taxed: {k.total_taxed}   Redist: {k.total_redistributed}   "
                 f"Rebel dodges: {k.total_rebel_dodges}")
        box_line(f"     Starvation ticks: {world.starvation_count} / "
                 f"{max(1, pop)*3} (overthrow threshold)")
        box_line(f"     Loyalty  : avg={avg_loyalty:.0f}   "
                 f"Loyal={loyal_count}   Rebels={rebel_count}")
    elif world.council:
        box_line(f" ⚖   INTERREGNUM — Council of {len(world.council)}")
        for cp in world.council:
            box_line(f"      {cp.name:<8}  INT:{cp.intelligence:<3}  "
                     f"Food:{cp.total_food_count():<3}  Loyalty:{cp.loyalty}")
    else:
        box_line(f" (No ruler yet — waiting for population ≥ 2)")

    # ══ People ════════════════════════════════════════════════════════════
    section("PEOPLE STATUS")

    for p in alive_people:
        # Status badge
        if getattr(p, 'is_king', False):
            badge = '👑'
        elif getattr(p, 'is_outcast', False):
            badge = '🚫 OUTCAST'
        elif getattr(p, 'is_rebel', False):
            badge = '⚡ REBEL'
        else:
            badge = ''

        gen    = stats.generation.get(p.name, 0)
        pnames = stats.parents.get(p.name, [])
        pstr   = ' & '.join(pnames) if pnames else 'founders'

        box_line(f" {p.name:<8} {badge}")
        box_line(f"   Age:{p.age:<4} INT:{p.intelligence:<4} LR:{p.learning_rate:<3} "
                 f"Gen:{gen}   Parents: {pstr}")
        box_line(f"   {bar('HP',p.health)}   {bar('Hunger',p.hunger)}")
        box_line(f"   Task: {p.current_task:<22}  Pos:({p.x},{p.y})")

        # Inventory breakdown
        inv_f  = p.inventory_count('food')
        inv_m  = p.inventory_count('meat')
        inv_h  = p.inventory_count('harvested')
        inv_s  = p.inventory_count('seed')
        inv_w  = p.inventory_count('wood')
        inv_st = p.inventory_count('stone')
        inv_fi = p.inventory_count('fiber')
        box_line(f"   Inv [{len(p.inventory)}/{p.max_inventory}]  "
                 f"Food:{inv_f}  Meat:{inv_m}  Harv:{inv_h}  Seed:{inv_s}  "
                 f"Wood:{inv_w}  Stone:{inv_st}  Fiber:{inv_fi}")

        # Farm info
        farm_str = (f"Farm @ ({p.farm_x},{p.farm_y})  Full:{p.farm_full}"
                    if p.has_farm else "No farm")
        box_line(f"   {farm_str}")

        # Cooldowns
        cd_parts = []
        if p.birth_cooldown > 0:
            cd_parts.append(f"BirthCD:{p.birth_cooldown}")
        if p.gather_cooldown > 0:
            cd_parts.append(f"GatherCD:{p.gather_cooldown}")
        if cd_parts:
            box_line(f"   {' | '.join(cd_parts)}")

        # Governance info (loyalty bar)
        if world.king is not None and p is not world.king.person:
            loy_str = loyalty_bar(getattr(p, 'loyalty', 50))
            rebel_str = '  ⚡ REBEL' if p.is_rebel else ''
            box_line(f"   Loyalty: {loy_str}{rebel_str}")

        # Lifetime stats
        box_line(f"   Children:{p.total_children}  Kills:{p.total_kills}  "
                 f"Ticks alive:{p.ticks_alive}")

        divider()

    # ══ Recent births ══════════════════════════════════════════════════════
    if recent_births:
        box_line(" 🍼  RECENT BIRTHS")
        for bt, bname, bparents in recent_births[-5:]:
            pstr = ' & '.join(bparents) if bparents else '?'
            box_line(f"    Tick {bt:<6}: {bname:<8}  parents: {pstr}")
        divider()

    # ══ Recent deaths ═════════════════════════════════════════════════════
    if recent_deaths:
        box_line(" 💀  RECENT DEATHS")
        for dt, dname, dage, dcause in recent_deaths[-5:]:
            box_line(f"    Tick {dt:<6}: {dname:<8}  age:{dage:<4}  cause: {dcause}")
        divider()

    # ══ Succession log ════════════════════════════════════════════════════
    if world.succession_log:
        box_line(" 👑  SUCCESSION LOG (last 6 events)")
        icons = {'crowned':'👑','died':'💀','overthrown':'⚡','elected':'🗳'}
        for st, sname, sreason in world.succession_log[-6:]:
            icon = icons.get(sreason, '?')
            box_line(f"    Tick {st:<6}: {sname:<8}  {icon} {sreason}")
        divider()

    # ══ Simulation health indicators ══════════════════════════════════════
    box_line(" 📊  SIMULATION METRICS")
    starving = sum(1 for p in alive_people if p.hunger <= 20)
    injured  = sum(1 for p in alive_people if p.health <= 50)
    farming  = sum(1 for p in alive_people if p.has_farm)
    avg_int  = (sum(p.intelligence for p in alive_people) / max(1, pop))
    avg_age  = (sum(p.age for p in alive_people) / max(1, pop))
    box_line(f"   Starving:{starving}  Injured:{injured}  Farming:{farming}  "
             f"Rebels:{rebel_count}")
    box_line(f"   Avg INT:{avg_int:.1f}   Avg Age:{avg_age:.1f}   "
             f"Total births:{stats.total_born}   Total deaths:{len(stats.deaths_log)}")

    bottom()
    print()

    # ── World map ─────────────────────────────────────────────────────────
    world.display()

    time.sleep(0.15)


# ─────────────────────────────────────────────────────────────────────────────
# END SCREEN
# ─────────────────────────────────────────────────────────────────────────────

os.system('cls' if os.name == 'nt' else 'clear')

longest = max(world.people, key=lambda p: p.age, default=None)
most_children = max(world.people, key=lambda p: p.total_children, default=None)
most_kills    = max(world.people, key=lambda p: p.total_kills, default=None)
smartest      = max(world.people, key=lambda p: p.intelligence, default=None)

top()
box_line(" CIVILISATION HAS ENDED")
divider()
box_line(f" Survived      : {tick} ticks")
box_line(f" Total born    : {stats.total_born}")
box_line(f" Peak pop      : {stats.peak_population}")
box_line(f" Total deaths  : {len(stats.deaths_log)}")
box_line(f" Huts built    : {stats.huts_built}")
box_line(f" Storehouses   : {stats.storehouses_built}")
box_line(f" Total rulers  : {len(world.succession_log)}")
if longest:
    box_line(f" Longest lived : {longest.name} (age {longest.age})")
if most_children and most_children.total_children > 0:
    box_line(f" Most children : {most_children.name} ({most_children.total_children})")
if most_kills and most_kills.total_kills > 0:
    box_line(f" Top hunter    : {most_kills.name} ({most_kills.total_kills} kills)")
if smartest:
    box_line(f" Smartest      : {smartest.name} (INT {smartest.intelligence})")

# ── Succession history ────────────────────────────────────────────────────────
section("SUCCESSION HISTORY")
icons = {'crowned':'👑','died':'💀','overthrown':'⚡','elected':'🗳'}
if world.succession_log:
    for st, sname, sreason in world.succession_log:
        icon      = icons.get(sreason, '?')
        style_str = ''
        if world.king and world.king.person.name == sname:
            style_str = f"  [{world.king.style_name}]"
        box_line(f"  Tick {st:<6}: {sname:<8}  {icon} {sreason}{style_str}")
else:
    box_line("  (no succession events)")

# ── Person summaries ──────────────────────────────────────────────────────────
section("PERSON SUMMARIES")
for p in world.people:
    gen    = stats.generation.get(p.name, 0)
    pnames = stats.parents.get(p.name, [])
    pstr   = ' & '.join(pnames) if pnames else 'founders'

    # Find death record
    drec = next(((dt,da,dc,di) for dt,dn,da,dc,di in stats.deaths_log
                 if dn == p.name), None)

    box_line(f" {p.name:<10}  Gen:{gen}   Parents: {pstr}")
    if drec:
        dt, da, dc, di = drec
        box_line(f"   Died tick {dt}  Age:{da}  INT at death:{di}  Cause: {dc}")
    else:
        box_line(f"   Survived  Age:{p.age}  INT:{p.intelligence}  LR:{p.learning_rate}")
    box_line(f"   Children:{p.total_children}  Kills:{p.total_kills}  "
             f"Ticks alive:{p.ticks_alive}")
    inv_f  = p.inventory_count('food')
    inv_m  = p.inventory_count('meat')
    inv_h  = p.inventory_count('harvested')
    inv_w  = p.inventory_count('wood')
    inv_st = p.inventory_count('stone')
    inv_fi = p.inventory_count('fiber')
    box_line(f"   Final inv: Food:{inv_f} Meat:{inv_m} Harv:{inv_h} "
             f"Wood:{inv_w} Stone:{inv_st} Fiber:{inv_fi}")
    divider()

# ── Births log ────────────────────────────────────────────────────────────────
section("FULL BIRTHS LOG")
for bt, bname, bparents in stats.births_log:
    pstr = ' & '.join(bparents) if bparents else 'founders'
    box_line(f"  Tick {bt:<6}: {bname:<8}  parents: {pstr}  "
             f"gen:{stats.generation.get(bname,0)}")

# ── Deaths log ────────────────────────────────────────────────────────────────
section("FULL DEATHS LOG")
if stats.deaths_log:
    for dt, dname, dage, dcause, dintel in stats.deaths_log:
        box_line(f"  Tick {dt:<6}: {dname:<8}  age:{dage:<4}  INT:{dintel:<4}  cause: {dcause}")
else:
    box_line("  (no deaths recorded)")

# ── Simulation evaluation ─────────────────────────────────────────────────────
section("SIMULATION EVALUATION")

if stats.total_born > 1:
    survival_rate = ((stats.total_born - len(stats.deaths_log)) / stats.total_born) * 100
else:
    survival_rate = 0.0

avg_lifespan = 0
if stats.deaths_log:
    avg_lifespan = sum(da for _,_,da,_,_ in stats.deaths_log) / len(stats.deaths_log)

king_count   = sum(1 for _,_,r in world.succession_log if r in ('crowned','elected'))
overthrows   = sum(1 for _,_,r in world.succession_log if r == 'overthrown')
natural_ends = sum(1 for _,_,r in world.succession_log if r == 'died')

max_gen = max((stats.generation.get(p.name,0) for p in world.people), default=0)

box_line(f" Ticks lasted       : {tick}")
box_line(f" Peak population    : {stats.peak_population}")
box_line(f" Survival rate      : {survival_rate:.1f}%")
box_line(f" Avg lifespan       : {avg_lifespan:.1f} age-units")
box_line(f" Generations reached: {max_gen}")
box_line(f" Total rulers       : {king_count}")
box_line(f" Overthrows         : {overthrows}")
box_line(f" Rulers died in office: {natural_ends}")
box_line(f" Huts built         : {stats.huts_built}")
box_line(f" Storehouses built  : {stats.storehouses_built}")
box_line(f" Total births       : {stats.total_born}")
box_line(f" Total deaths       : {len(stats.deaths_log)}")
if stats.total_born > 0:
    box_line(f" Net growth         : {stats.total_born - len(stats.deaths_log):+d} people")

# Health score (0–100 composite)
health_score = 0
health_score += min(30, stats.peak_population * 2)
health_score += min(20, int(survival_rate / 5))
health_score += min(15, max_gen * 3)
health_score += min(20, (stats.huts_built + stats.storehouses_built) * 4)
health_score += min(15, tick // 100)
health_score  = min(100, health_score)

box_line(f"")
box_line(f" ★ Civilisation health score: {health_score}/100")
if health_score >= 80:
    box_line(f"   Rating: THRIVING 🌟")
elif health_score >= 55:
    box_line(f"   Rating: STABLE 🏡")
elif health_score >= 30:
    box_line(f"   Rating: STRUGGLING 🌾")
else:
    box_line(f"   Rating: COLLAPSED 💀")

bottom()