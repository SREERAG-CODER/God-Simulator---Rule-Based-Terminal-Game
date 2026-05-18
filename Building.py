class BuildSite:
    """
    A construction project on the map.
    Multiple people can walk here and deposit materials to complete it.
    """
    RECIPES = {
        'hut':        {'wood': 5, 'fiber': 3},
        'storehouse': {'wood': 8, 'stone': 4},
    }

    def __init__(self, kind, x, y):
        self.kind   = kind          # 'hut' or 'storehouse'
        self.x      = x
        self.y      = y
        self.symbol = 'B'
        self.needed = dict(self.RECIPES[kind])   # remaining materials needed
        self.complete = False

    def contribute(self, person):
        """
        Person walks to site and deposits whatever materials are still needed.
        Returns True if they contributed anything.
        """
        contributed = False
        for resource, amount in list(self.needed.items()):
            if amount <= 0:
                continue
            item_name = resource          # 'wood', 'stone', 'fiber'
            while self.needed[resource] > 0 and person.has_item(item_name):
                person.remove_item(item_name)
                self.needed[resource] -= 1
                contributed = True

        if all(v <= 0 for v in self.needed.values()):
            self.complete = True

        return contributed

    def is_complete(self):
        return self.complete


class Hut:
    """
    Placed building: heals nearby people passively each tick.
    Also raises the world population cap.
    """
    POP_BONUS   = 5
    HEAL_RADIUS = 6
    HEAL_AMOUNT = 2     # HP restored per tick to nearby injured people

    def __init__(self, x, y):
        self.x      = x
        self.y      = y
        self.symbol = 'H'

    def apply_healing(self, world):
        for person in world.people:
            if not person.isAlive:
                continue
            dist = abs(person.x - self.x) + abs(person.y - self.y)
            if dist <= self.HEAL_RADIUS and person.health < 100:
                person.health = min(100, person.health + self.HEAL_AMOUNT)


class Storehouse:
    """
    Shared food depot on the map.
    People deposit surplus food here and withdraw when starving.
    """
    INTERACT_RADIUS = 3

    def __init__(self, x, y):
        self.x         = x
        self.y         = y
        self.symbol    = 'S'
        self.inventory = []    # list of item strings: 'food','harvested','meat'
        self.capacity  = 200

    # ── Deposit ──────────────────────────────────────────────────────────────
    def deposit(self, person):
        """
        If person has more than 10 food items total, deposit the surplus.
        Returns number of items deposited.
        """
        food_items = [i for i in person.inventory if i in ('food', 'harvested', 'meat')]
        surplus    = len(food_items) - 10
        if surplus <= 0:
            return 0

        deposited = 0
        # Deposit least-valuable first: food → harvested → meat
        for item_type in ('food', 'harvested', 'meat'):
            while surplus > 0 and person.has_item(item_type) and len(self.inventory) < self.capacity:
                person.remove_item(item_type)
                self.inventory.append(item_type)
                surplus   -= 1
                deposited += 1

        return deposited

    # ── Withdraw ─────────────────────────────────────────────────────────────
    def withdraw(self, person, amount=3):
        """
        Give up to `amount` food items to a hungry person.
        Returns number of items given.
        """
        given = 0
        # Withdraw best food first: meat → harvested → food
        for item_type in ('meat', 'harvested', 'food'):
            while given < amount and item_type in self.inventory:
                if person.add_to_inventory(item_type):
                    self.inventory.remove(item_type)
                    given += 1
                else:
                    break
        return given

    def is_empty(self):
        return len(self.inventory) == 0

    def food_count(self):
        return len(self.inventory)