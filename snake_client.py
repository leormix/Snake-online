import asyncio
import json
import pygame
import websockets
import time

WINDOW_WIDTH, WINDOW_HEIGHT = 850, 650
BG_COLOR = (0, 0, 0)
FPS = 60

BONUS_COLORS = {
    "TURTLE": (0, 200, 0),
    "TURBO": (255, 215, 0),
    "REVERSE": (255, 0, 255),
    "GHOST": (255, 255, 255),
    "MIRROR": (0, 255, 255),
    "GROW": (255, 165, 0),
    "SHRINK": (150, 0, 255)
}

def key_to_input(key, player_id):
    if player_id == 1:
        if key == pygame.K_LEFT:  return {"key": "LEFT"}
        if key == pygame.K_RIGHT: return {"key": "RIGHT"}
        if key == pygame.K_UP:    return {"key": "UP"}
        if key == pygame.K_DOWN:  return {"key": "DOWN"}
    else:
        if key == pygame.K_a: return {"key": "A"}
        if key == pygame.K_d: return {"key": "D"}
        if key == pygame.K_w: return {"key": "W"}
        if key == pygame.K_s: return {"key": "S"}
    return None


class Client:
    def __init__(self, uri="ws://localhost:8080"):
        self.uri = uri
        self.player_id = None
        self.state = None
        self.prev_state = None
        self.last_update_time = time.time()

        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Snake Multiplayer")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 20)
        self.font_small = pygame.font.SysFont("consolas", 16)

    async def connect(self):
        try:
            async with websockets.connect(self.uri) as ws:
                msg = json.loads(await ws.recv())
                if msg.get("type") == "full":
                    print("Server full.")
                    return
                if msg.get("type") == "welcome":
                    self.player_id = msg["player"]
                    print(f"You are Player {self.player_id}")

                recv_task = asyncio.create_task(self.receiver(ws))
                input_task = asyncio.create_task(self.sender(ws))
                await asyncio.gather(recv_task, input_task)
        except Exception as e:
            print("Connection error:", e)

    async def receiver(self, ws):
        try:
            async for msg in ws:
                data = json.loads(msg)
                if data.get("type") == "state":
                    self.prev_state = self.state
                    self.state = data["data"]
                    self.last_update_time = time.time()
        except Exception as e:
            print("Receiver error:", e)

    async def sender(self, ws):
        while True:
            await asyncio.sleep(0.016)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        await ws.send(json.dumps({"type": "reset"}))
                    else:
                        inp = key_to_input(event.key, self.player_id)
                        if inp:
                            await ws.send(json.dumps({"type": "input", "data": inp}))
            self.draw()

    def interpolate_coord(self, prev, curr, alpha, max_value):
        diff = curr - prev
        if abs(diff) > max_value / 2:
            if diff > 0:
                prev += max_value
            else:
                curr += max_value
        return (prev + (curr - prev) * alpha) % max_value

    def draw_legend(self):
        y = 5
        x = 10
        self.screen.blit(self.font.render("Бонусы:", True, (200, 200, 200)), (x, y))
        x += 90
        for btype, color in BONUS_COLORS.items():
            pygame.draw.rect(self.screen, color, (x, y + 5, 20, 20))
            self.screen.blit(self.font_small.render(btype, True, (220, 220, 220)), (x + 25, y + 5))
            x += 90

    def draw(self):
        if not self.state:
            return

        alpha = min((time.time() - self.last_update_time) * 12, 1.0)
        self.screen.fill(BG_COLOR)
        self.draw_legend()

        meta = self.state["meta"]
        snakes = self.state["snakes"]
        food = self.state["food"]
        bonuses = self.state.get("bonuses", [])

        pygame.draw.rect(self.screen, food["color"],
                         (food["x"], food["y"] + 50, meta["square"], meta["square"]))
        for b in bonuses:
            pygame.draw.rect(self.screen, b["color"],
                             (b["x"], b["y"] + 50, meta["square"], meta["square"]))

        for i, s in enumerate(snakes):
            if self.prev_state:
                prev_s = self.prev_state["snakes"][i]
                x = self.interpolate_coord(prev_s["x"], s["x"], alpha, meta["width"])
                y = self.interpolate_coord(prev_s["y"], s["y"], alpha, meta["height"])
            else:
                x, y = s["x"], s["y"]

            tail = []
            if self.prev_state:
                prev_tail = self.prev_state["snakes"][i]["tail"]
                curr_tail = s["tail"]
                for j in range(min(len(prev_tail), len(curr_tail))):
                    tx = self.interpolate_coord(prev_tail[j][0], curr_tail[j][0], alpha, meta["width"])
                    ty = self.interpolate_coord(prev_tail[j][1], curr_tail[j][1], alpha, meta["height"])
                    tail.append((tx, ty))
            else:
                tail = s["tail"]

            for idx, seg in enumerate(tail):
                shade = max(50, 255 - idx * 15)
                color = tuple(max(0, c - (255 - shade)) for c in s["color"])
                pygame.draw.rect(self.screen, color, (seg[0], seg[1] + 50, meta["square"], meta["square"]))

            pygame.draw.rect(self.screen, s["color"], (x, y + 50, meta["square"], meta["square"]))

            if s["bonus"]:
                seconds_left = max(0, int(s["timer"] / 8))
                text = f"{s['bonus']} ({seconds_left}s)"
                label = self.font_small.render(text, True, (255, 255, 255))
                self.screen.blit(label, (10, 30 + i * 18))

        pygame.display.flip()
        self.clock.tick(FPS)


if __name__ == "__main__":
    uri = input("Server (ws://localhost:8080): ").strip() or "ws://localhost:8080"
    client = Client(uri)
    asyncio.run(client.connect())
