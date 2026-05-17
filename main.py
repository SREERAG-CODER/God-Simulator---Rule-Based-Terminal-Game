from World import World

world = World(30, 30)
person = world.spawn_person("Adam")
print(f"\n{person.name} spawned at ({person.x}, {person.y})")
world.display()
