# King.py
# Governs the civilisation: sets build zone, collects taxes, can be overthrown.
# King personality is derived from intelligence + a random coronation modifier.

import random

# ── Build zone ────────────────────────────────────────────────────────────────
INITIAL_BUILD_RADIUS   = 10
RADIUS_GROWTH_PER_POP  = 5    # +5 radius for every 5 people
RADIUS_POP_STEP        = 5

# ── Taxation (base defaults — overridden per style) ───────────────────────────
TAX_INTERVAL           = 100  # ticks between tax collection cycles

# ── Overthrow ─────────────────────────────────────────────────────────────────
STARVATION_THRESHOLD_PER_PERSON = 3
LOYALTY_REBEL_THRESHOLD         = 25
LOYALTY_LOYAL_THRESHOLD         = 75

# ── Loyalty drift ─────────────────────────────────────────────────────────────
LOYALTY_GAIN_WELL_FED        =  1
LOYALTY_LOSS_STARVING        = -2
LOYALTY_LOSS_TAXED           = -3
LOYALTY_GAIN_REDISTRIB       =  5
LOYALTY_LOSS_KING_WEAK       = -1
LOYALTY_GAIN_FED_BY_KING     =  8


# ══════════════════════════════════════════════════════════════════════════════
# Ruling style profiles
# Each style defines concrete numeric behaviour for the King.
# ══════════════════════════════════════════════════════════════════════════════

STYLES = {
    # name            tax_amount  leniency  adapt  starvation_skip  radius_eagerness
    # tax_amount        : food items collected per person per cycle
    # leniency          : surplus a person must have ABOVE tax before they're taxed
    #                     (higher = king gives more slack to poor people)
    # adapt_speed       : multiplier on LR when adjusting tax rate (0 = never adapts)
    # starvation_skip   : if this fraction of pop is starving, skip tax this cycle
    #                     (0.0 = never skips, 1.0 = always skips when anyone starving)
    # radius_eagerness  : extra radius added proactively per 3 people (0 = reactive only)
    'Ruthless Brute':   dict(tax_amount=3, leniency=1, adapt_speed=0.0, starvation_skip=0.0, radius_eagerness=0),
    'Brute':            dict(tax_amount=2, leniency=2, adapt_speed=0.0, starvation_skip=0.0, radius_eagerness=1),
    'Firm':             dict(tax_amount=2, leniency=3, adapt_speed=0.5, starvation_skip=0.1, radius_eagerness=2),
    'Balanced':         dict(tax_amount=1, leniency=3, adapt_speed=1.0, starvation_skip=0.2, radius_eagerness=3),
    'Wise':             dict(tax_amount=1, leniency=4, adapt_speed=1.5, starvation_skip=0.3, radius_eagerness=4),
    'Benevolent Wise':  dict(tax_amount=1, leniency=5, adapt_speed=2.0, starvation_skip=0.4, radius_eagerness=5),
}

# Ordered list for stepping up/down
STYLE_ORDER = [
    'Ruthless Brute',
    'Brute',
    'Firm',
    'Balanced',
    'Wise',
    'Benevolent Wise',
]

def _derive_style(person):
    """
    Base style from intelligence, then shift by a random coronation modifier.
    Returns (style_name, modifier_applied).
    """
    intel = person.intelligence

    if intel < 50:
        base_idx = 0   # Ruthless Brute
    elif intel < 80:
        base_idx = 2   # Firm
    elif intel < 120:
        base_idx = 3   # Balanced
    else:
        base_idx = 4   # Wise

    # Random modifier: -1 / 0 / +1, weighted so 0 is most likely
    modifier = random.choices([-1, 0, 1], weights=[25, 50, 25])[0]
    final_idx = max(0, min(len(STYLE_ORDER) - 1, base_idx + modifier))

    return STYLE_ORDER[final_idx], modifier


# ══════════════════════════════════════════════════════════════════════════════
# King class
# ══════════════════════════════════════════════════════════════════════════════

class King:
    """
    Wraps a Person reference and adds governance behaviour.
    The Person still ticks normally; King adds an extra governance layer on top.
    """

    def __init__(self, person, world_tick):
        self.person        = person
        self.capital_x     = person.x
        self.capital_y     = person.y
        self.build_radius  = INITIAL_BUILD_RADIUS
        self.reign_ticks   = 0
        self.crowned_tick  = world_tick
        self.tax_timer     = 0
        self.total_taxed             = 0
        self.total_redistributed     = 0
        self.total_rebel_dodges      = 0

        # ── Derive personality ────────────────────────────────────────────
        self.style_name, self.coronation_modifier = _derive_style(person)
        profile = STYLES[self.style_name]

        self.tax_amount        = profile['tax_amount']        # current (can adapt)
        self._base_tax_amount  = profile['tax_amount']        # anchor for adaptation
        self.leniency          = profile['leniency']
        self.adapt_speed       = profile['adapt_speed']
        self.starvation_skip   = profile['starvation_skip']
        self.radius_eagerness  = profile['radius_eagerness']

        # Adaptation memory: track last cycle's starvation fraction
        self._last_starving_fraction = 0.0

        # Mark the person
        person.symbol  = 'K'
        person.is_king = True

    # ── Build zone ────────────────────────────────────────────────────────────
    def update_build_radius(self, population):
        """
        Base expansion from population.
        Eager rulers (high radius_eagerness) add a proactive bonus on top.
        """
        base_bonus  = (population // RADIUS_POP_STEP) * RADIUS_GROWTH_PER_POP
        eager_bonus = (population // 3) * self.radius_eagerness
        self.build_radius = INITIAL_BUILD_RADIUS + base_bonus + eager_bonus

    def in_build_zone(self, x, y):
        return (abs(x - self.capital_x) + abs(y - self.capital_y)) <= self.build_radius

    # ── Adaptation ────────────────────────────────────────────────────────────
    def _adapt_tax_rate(self, world):
        """
        Adaptive kings (adapt_speed > 0) adjust tax_amount each cycle based on
        how bad starvation was last cycle and the king's learning_rate.

        Formula:
          effective_adapt = adapt_speed * (learning_rate / 4)
          If starvation fraction > starvation_skip threshold → lower tax by 1
          If starvation fraction == 0 and storehouse well-stocked → raise by 1
          Always clamped to [1, base_tax_amount + 2]
        """
        if self.adapt_speed == 0:
            return  # Brutes never adapt

        lr     = self.person.learning_rate
        factor = self.adapt_speed * (lr / 4.0)

        pop            = max(1, len(world.people))
        starving_now   = sum(1 for p in world.people if p.isAlive and p.hunger <= 20)
        starving_frac  = starving_now / pop

        stored = world.total_stored_food()

        if starving_frac > self.starvation_skip and random.random() < factor:
            # People are suffering — compassionate/wise king reduces tax
            self.tax_amount = max(1, self.tax_amount - 1)
        elif starving_frac == 0 and stored > pop * 3 and random.random() < factor * 0.5:
            # Storehouse overflowing, nobody starving — raise tax back toward base
            self.tax_amount = min(self._base_tax_amount + 2, self.tax_amount + 1)

        self._last_starving_fraction = starving_frac

    # ── Taxation ──────────────────────────────────────────────────────────────
    def collect_taxes(self, world):
        self.tax_timer += 1
        if self.tax_timer < TAX_INTERVAL:
            return

        self.tax_timer = 0

        if not world.storehouses:
            return

        # ── Adaptive kings may skip the whole cycle if starvation is bad ──
        pop           = max(1, len(world.people))
        starving      = sum(1 for p in world.people if p.isAlive and p.hunger <= 20)
        starving_frac = starving / pop

        if starving_frac >= self.starvation_skip and self.starvation_skip > 0:
            # King voluntarily waives taxes this cycle
            self._redistribute(world)
            self._adapt_tax_rate(world)
            return

        # ── Adapt before collecting ────────────────────────────────────────
        self._adapt_tax_rate(world)

        rebel_dodges = 0

        for person in world.people:
            if not person.isAlive:
                continue
            if person is self.person:
                continue

            food_count  = person.total_food_count()
            has_surplus = food_count > self.tax_amount + self.leniency

            # Rebel with food: dodges, king looks weak
            if getattr(person, 'is_rebel', False):
                if has_surplus:
                    rebel_dodges += 1
                continue

            # Loyal but poor: skip silently
            if not has_surplus:
                continue

            # Loyal with surplus: collect
            sh = world.nearest_storehouse(person.x, person.y)
            if sh is None:
                continue

            collected = 0
            for item in ('food', 'harvested', 'meat'):
                while collected < self.tax_amount and person.has_item(item):
                    person.remove_item(item)
                    sh.inventory.append(item)
                    collected += 1
                    self.total_taxed += 1
                if collected >= self.tax_amount:
                    break

            if collected > 0:
                person.loyalty = max(0, person.loyalty + LOYALTY_LOSS_TAXED)

        # Rebel dodges weaken the king's image
        if rebel_dodges > 0:
            for person in world.people:
                if not person.isAlive or person is self.person:
                    continue
                if not getattr(person, 'is_rebel', False):
                    penalty = LOYALTY_LOSS_KING_WEAK * rebel_dodges
                    person.loyalty = max(0, person.loyalty + penalty)
            self.total_rebel_dodges += rebel_dodges

        self._redistribute(world)

    def _redistribute(self, world):
        """Feed the starving from the storehouse."""
        if not world.storehouses:
            return
        for person in world.people:
            if not person.isAlive:
                continue
            if person.hunger > 20 or person.has_edible_food():
                continue
            sh = world.nearest_storehouse(person.x, person.y)
            if sh is None or sh.is_empty():
                continue
            given = sh.withdraw(person, amount=2)
            if given:
                self.total_redistributed += given
                person.loyalty = min(100, person.loyalty + LOYALTY_GAIN_FED_BY_KING)

    # ── Overthrow check ───────────────────────────────────────────────────────
    def check_overthrow(self, world):
        threshold = max(1, len(world.people)) * STARVATION_THRESHOLD_PER_PERSON
        return world.starvation_count >= threshold

    # ── Per-tick update ───────────────────────────────────────────────────────
    def tick(self, world, tick_num):
        if not self.person.isAlive:
            return
        self.reign_ticks += 1
        self.update_build_radius(len(world.people))
        self.collect_taxes(world)


# ── Loyalty helpers ───────────────────────────────────────────────────────────

def update_loyalties(world):
    if world.king is None:
        return
    for person in world.people:
        if not person.isAlive:
            continue
        if person is world.king.person:
            continue
        if person.hunger <= 20:
            person.loyalty = max(0, person.loyalty + LOYALTY_LOSS_STARVING)
            world.starvation_count += 1
        elif person.hunger > 50:
            person.loyalty = min(100, person.loyalty + LOYALTY_GAIN_WELL_FED)
        person.is_rebel = person.loyalty < LOYALTY_REBEL_THRESHOLD


# ── Succession ────────────────────────────────────────────────────────────────

def form_council(world):
    candidates = [p for p in world.people
                  if p.isAlive and p is not getattr(world.king, 'person', None)]
    candidates.sort(key=lambda p: p.intelligence, reverse=True)
    world.council = candidates[:3]


def elect_new_king(world, tick_num):
    if not world.council:
        return None

    def wealth(p):
        return (p.total_food_count() +
                p.inventory_count('wood') +
                p.inventory_count('stone') +
                p.inventory_count('fiber'))

    world.council.sort(key=wealth, reverse=True)
    chosen = world.council[0]

    if world.king is not None:
        old            = world.king.person
        old.symbol     = 'O'
        old.is_king    = False
        old.is_outcast = True

    world.king             = King(chosen, tick_num)
    world.council          = []
    world.starvation_count = 0

    world.succession_log.append((tick_num, chosen.name, 'elected'))
    return world.king