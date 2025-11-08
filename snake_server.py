import asyncio
import json
import random
import websockets

WINDOW_WIDTH, WINDOW_HEIGHT = 800, 600
SQUARE_SIZE = 20
FPS = 8

# Типы бонусов и их цвета
BONUS_COLORS = {
    "TURTLE": (0, 200, 0),     
    "TURBO": (255, 215, 0),    
    "REVERSE": (255, 0, 255),  
    "GHOST": (255, 255, 255),  
    "MIRROR": (0, 255, 255),   
    "GROW": (255, 165, 0),     
    "SHRINK": (150, 0, 255)   
}

def grid_random():
    gx = random.randint(0, (WINDOW_WIDTH - SQUARE_SIZE) // SQUARE_SIZE) * SQUARE_SIZE
    gy = random.randint(0, (WINDOW_HEIGHT - SQUARE_SIZE) // SQUARE_SIZE) * SQUARE_SIZE
    return gx, gy


class Snake:
    def __init__(self, x, y, dx, dy, color):
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.tail = []
        self.length = 1
        self.color = color
        self.bonus = None
        self.bonus_timer = 0
        self.speed = 1
        self.slow = False
        self.ghost = False
        self.mirror = False

    def apply_bonus(self, btype, duration_ticks=FPS * 7):
        self.bonus = btype
        self.bonus_timer = duration_ticks
        if btype == "GROW":
            self.length += 3
        elif btype == "SHRINK":
            self.length = max(1, self.length - 3)
        if btype == "TURBO":
            self.speed = 2
            self.slow = False
            self.ghost = False
            self.mirror = False
        elif btype == "TURTLE":
            self.slow = True
            self.speed = 1
            self.ghost = False
            self.mirror = False
        elif btype == "REVERSE":
            pass
        elif btype == "GHOST":
            self.ghost = True
        elif btype == "MIRROR":
            self.mirror = True

    def clear_bonus(self):
        self.bonus = None
        self.bonus_timer = 0
        self.speed = 1
        self.slow = False
        self.ghost = False
        self.mirror = False


class GameState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.s1 = Snake(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2, SQUARE_SIZE, 0, (0, 200, 0))
        self.s2 = Snake(WINDOW_WIDTH // 4, WINDOW_HEIGHT // 2, SQUARE_SIZE, 0, (0, 0, 200))
        self.food_x, self.food_y = grid_random()
        self.bonuses = []
        self.running = True
        self.tick = 0

    def spawn_bonus(self):
        if random.random() < 0.02 and len(self.bonuses) < 3:
            bx, by = grid_random()
            btype = random.choice(list(BONUS_COLORS.keys()))
            bcolor = BONUS_COLORS[btype]
            self.bonuses.append({"x": bx, "y": by, "type": btype, "color": bcolor})

    def move_snake_once(self, s):
        s.tail.insert(0, (s.x, s.y))
        s.tail = s.tail[:s.length]
        s.x = (s.x + s.dx) % WINDOW_WIDTH
        s.y = (s.y + s.dy) % WINDOW_HEIGHT

    def step(self):
        self.tick += 1
        for s in (self.s1, self.s2):
            moves = s.speed
            if s.slow:
                if self.tick % 2 == 0:
                    moves = 1
                else:
                    moves = 0
            for _ in range(moves):
                self.move_snake_once(s)

        for s in (self.s1, self.s2):
            if s.x == self.food_x and s.y == self.food_y:
                s.length += 1
                self.food_x, self.food_y = grid_random()

            for b in list(self.bonuses):
                if s.x == b["x"] and s.y == b["y"]:
                    s.apply_bonus(b["type"], duration_ticks=FPS * 7)
                    self.bonuses.remove(b)

        for s in (self.s1, self.s2):
            if s.bonus_timer > 0:
                s.bonus_timer -= 1
                if s.bonus_timer <= 0:
                    s.clear_bonus()

        if not self.s1.ghost:
            if (self.s1.x, self.s1.y) in self.s1.tail[1:] or (self.s1.x, self.s1.y) in self.s2.tail:
                self.running = False
        if not self.s2.ghost:
            if (self.s2.x, self.s2.y) in self.s2.tail[1:] or (self.s2.x, self.s2.y) in self.s1.tail:
                self.running = False
        if (self.s1.x, self.s1.y) == (self.s2.x, self.s2.y) and not (self.s1.ghost or self.s2.ghost):
            self.running = False

        self.spawn_bonus()

    def to_dict(self):
        return {
            "running": self.running,
            "food": {"x": self.food_x, "y": self.food_y, "color": (255, 0, 0)},
            "bonuses": self.bonuses,
            "snakes": [
                {"x": self.s1.x, "y": self.s1.y, "tail": self.s1.tail,
                 "color": self.s1.color, "bonus": self.s1.bonus, "timer": self.s1.bonus_timer,
                 "speed": self.s1.speed, "ghost": self.s1.ghost, "mirror": self.s1.mirror},
                {"x": self.s2.x, "y": self.s2.y, "tail": self.s2.tail,
                 "color": self.s2.color, "bonus": self.s2.bonus, "timer": self.s2.bonus_timer,
                 "speed": self.s2.speed, "ghost": self.s2.ghost, "mirror": self.s2.mirror},
            ],
            "meta": {"width": WINDOW_WIDTH, "height": WINDOW_HEIGHT, "square": SQUARE_SIZE}
        }


class SnakeServer:
    def __init__(self):
        self.state = GameState()
        self.clients = {}
        self.inputs = {1: None, 2: None}

    async def handler(self, ws):
        if 1 not in self.clients:
            pid = 1
        elif 2 not in self.clients:
            pid = 2
        else:
            await ws.send(json.dumps({"type": "full"}))
            await ws.close()
            return

        self.clients[pid] = ws
        await ws.send(json.dumps({"type": "welcome", "player": pid}))
        print(f"[Server] Player {pid} connected")

        try:
            async for msg in ws:
                data = json.loads(msg)
                if data.get("type") == "input":
                    self.inputs[pid] = data.get("data")
                elif data.get("type") == "reset":
                    self.state = GameState()
        except Exception:
            pass
        finally:
            print(f"[Server] Player {pid} disconnected")
            self.clients.pop(pid, None)
            self.inputs[pid] = None

    def apply_inputs(self):
        self.apply_input_to_snake(self.state.s1, self.inputs[1])
        self.apply_input_to_snake(self.state.s2, self.inputs[2],
                                  {"A": "LEFT", "D": "RIGHT", "W": "UP", "S": "DOWN"})

    def apply_input_to_snake(self, s, inp, mapping=None):
        if not inp:
            return
        k = inp.get("key")
        if mapping:
            k = mapping.get(k, None)
        if s.bonus == "REVERSE":
            if k == "LEFT": k = "RIGHT"
            elif k == "RIGHT": k = "LEFT"
            elif k == "UP": k = "DOWN"
            elif k == "DOWN": k = "UP"
        if k == "LEFT" and s.dx == 0:
            s.dx, s.dy = -SQUARE_SIZE, 0
        elif k == "RIGHT" and s.dx == 0:
            s.dx, s.dy = SQUARE_SIZE, 0
        elif k == "UP" and s.dy == 0:
            s.dx, s.dy = 0, -SQUARE_SIZE
        elif k == "DOWN" and s.dy == 0:
            s.dx, s.dy = 0, SQUARE_SIZE

    async def broadcast(self, payload):
        data = json.dumps(payload)
        for ws in list(self.clients.values()):
            try:
                await ws.send(data)
            except Exception:
                pass

    async def game_loop(self):
        while True:
            await asyncio.sleep(1 / FPS)
            self.apply_inputs()
            if self.state.running:
                self.state.step()
            await self.broadcast({"type": "state", "data": self.state.to_dict()})


async def main():
    server = SnakeServer()
    async with websockets.serve(server.handler, "0.0.0.0", 8080):
        print("[Server] Running on port 8080")
        await server.game_loop()


if __name__ == "__main__":
    asyncio.run(main())
