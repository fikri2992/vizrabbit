"""End-to-end check of the live activity stream against a real uvicorn server.

Not a pytest test: the endpoint is an endless generator, and TestClient never
signals disconnect, so consuming it under TestClient hangs instead of failing.
A real server does the disconnect handshake properly, so this drives one.

    uv run python -m scripts.check_sse
"""

import asyncio
import base64
import json
import sys
import threading

import httpx
import itsdangerous
import uvicorn

from app.api.auth import SESSION_USER_KEY
from app.api.deps import get_store
from app.api.main import app
from app.config import settings
from app.domain.entities import Member, Project, Role
from app.infra import repository as repo
from app.infra.events import Event, bus

PORT = 8123
USER = {"id": "u-owner", "email": "owner@acme.com", "name": "Ola Owner", "picture": ""}
PROJECT_ID = "sse-check"


def session_cookie() -> str:
    signer = itsdangerous.TimestampSigner(settings.session_secret)
    payload = base64.b64encode(json.dumps({SESSION_USER_KEY: USER}).encode())
    return signer.sign(payload).decode()


async def main() -> int:
    store = get_store()
    await repo.save(
        store,
        Project(
            id=PROJECT_ID,
            name="SSE check",
            members=[Member(user_id=USER["id"], email=USER["email"], role=Role.OWNER)],
        ),
    )

    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.1)
    else:
        print("FAIL: server did not start")
        return 1

    failures = []
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{PORT}", cookies={"session": session_cookie()}, timeout=10
        ) as client, client.stream("GET", f"/api/projects/{PROJECT_ID}/events") as response:
            if response.status_code != 200:
                print(f"FAIL: stream returned {response.status_code}")
                return 1
            print(f"connected: {response.headers['content-type']}")

            lines = response.aiter_lines()
            await asyncio.wait_for(anext(lines), timeout=5)  # ": connected"

            stages = ["scan_started", "annotating", "run_finished"]
            for stage in stages:
                await bus.publish(
                    Event(stage=stage, project_id=PROJECT_ID, run_id="r1", detail={"pin": 1})
                )

            received = []
            deadline = asyncio.get_running_loop().time() + 10
            while len(received) < len(stages):
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                line = await asyncio.wait_for(anext(lines), timeout=remaining)
                if line.startswith("data: "):
                    received.append(json.loads(line[6:])["stage"])

            print(f"received: {received}")
            if received != stages:
                failures.append(f"expected {stages}, received {received}")

        # The server must let go of the subscription once the client disconnects.
        await asyncio.sleep(0.5)
        if bus.subscriber_count(PROJECT_ID) != 0:
            failures.append(
                f"subscription leaked: {bus.subscriber_count(PROJECT_ID)} still registered"
            )
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    print("\nSSE check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
