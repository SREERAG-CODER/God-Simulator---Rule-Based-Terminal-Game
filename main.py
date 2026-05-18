import time
import os
from World import World

def draw_bar(label, value, max_value=100, length=20):
    filled = int((value / max_value) * length)
    bar = '█' * filled + '░' * (length - filled)
    return f"{label}: [{bar}] {value}/{max_value}"

world = World(30, 30)
person = world.spawn_person("Adam")

tick = 0
while person.isAlive:
    os.system('cls')
    tick += 1

    # core updates
    person.update_hunger(tick)
    person.age_up(tick)
    person.intelligence_gain(tick)

    # priority decision tree
    if person.hunger < 30 and not person.has_edible_food():
        # critical hunger — hunt, but still move if no animal found
        person.hunt(world)
        if person.current_task == 'hunting':
            person.move(world, tick)
    else:
        if person.has_farm:
            person.try_harvest(world)
            # only roam if NOT walking toward a harvest
            if person.current_task != 'harvesting':
                person.try_collect_seed(world)
                person.try_plant(world)
                person.move(world, tick)
        else:
            person.try_collect_seed(world)
            person.try_plant(world)
            person.move(world, tick)

    # world updates
    world.grow_farms()
    world.update_animals(tick)

    if tick % 50 == 0:
        world.respawn_animals()

    # display
    inv_food      = person.inventory_count('food')
    inv_meat      = person.inventory_count('meat')
    inv_harvested = person.inventory_count('harvested')
    inv_seed      = person.inventory_count('seed')

    print(f"  ╔══════════════════════════════════════════════════════╗")
    print(f"  ║  {person.name:<10} | Tick: {tick:<6} | Age: {person.age:<4}          ║")
    print(f"  ║  {draw_bar('Health', person.health)}              ║")
    print(f"  ║  {draw_bar('Hunger', person.hunger)}              ║")
    print(f"  ║  Intel: {person.intelligence:<4}/200 | Task: {person.current_task:<12}    ║")
    print(f"  ║  Inv [{len(person.inventory)}/25]: Food={inv_food} Meat={inv_meat} Harvest={inv_harvested} Seeds={inv_seed}  ║")
    print(f"  ║  Farm: {'Yes' if person.has_farm else 'No':<4} | Full: {'Yes' if person.farm_full else 'No':<4}                     ║")
    print(f"  ╚══════════════════════════════════════════════════════╝")
    print()
    world.display()

    time.sleep(0.3)

os.system('cls')
print(f"""
  ╔══════════════════════════════════════════════╗
  ║         {person.name} HAS DIED                      ║
  ║         Survived {tick} ticks                     ║
  ║         Reached Age: {person.age}                    ║
  ║         Max Intelligence: {person.intelligence}              ║
  ╚══════════════════════════════════════════════╝
""")