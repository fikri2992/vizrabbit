"""Generate candidate images for the eval set.

Important: this script produces *candidates*, not labels. Generators frequently
ignore a request for a specific flaw, and just as often introduce a different one.
Labelling what was prompted rather than what is actually visible would corrupt the
benchmark in the exact direction that flatters the pipeline.

So: generate here, then open each image, write down what you can actually see, and
put that in eval/labels.json. Prompts are grouped only to bias the odds of getting
a spread of failure modes.

    uv run python -m scripts.generate_eval_images --count 30 --out ../eval/images
"""

import argparse
import asyncio
import sys
from pathlib import Path

from google import genai

from app.config import settings

MODEL = "gemini-3.1-flash-image"

#: Prompts chosen to stress the failure modes the built-in guideline covers.
#: "hard" prompts crowd the frame with hands, text and interaction; "clean" prompts
#: are simple compositions a generator usually gets right.
HARD_PROMPTS = [
    "Close-up product photo: a woman's hands holding and opening a glass skincare jar, "
    "fingers wrapped around the lid, studio lighting, e-commerce style",
    "A barista's hands pouring latte art into a ceramic cup, overhead shot, both hands visible",
    "Two people shaking hands over a desk while holding coffee cups, office background",
    "A model wearing a knitted jumper holding a smartphone up to show the screen, hands in frame",
    "Street market stall with handwritten price signs and labelled jars, shoppers browsing",
    "A chef chopping vegetables with a knife, both hands on the board, close-up",
    "Group of four friends toasting with glasses at a restaurant table, hands and glasses "
    "overlapping",
    "A watch on a wrist being adjusted by the other hand, macro product shot",
    "A cyclist gripping handlebars, gloved hands, city street reflections in shop windows",
    "Woman applying lipstick in front of a mirror, reflection visible, hand near face",
    "A cluttered desk with an open laptop showing a website, sticky notes with writing, mug "
    "and plant",
    "Someone carrying four shopping bags with branded logos, walking through a mall",
    "A jeweller setting a ring with tweezers under a magnifying lamp, fingers in frame",
    "Family of five posing on a sofa, arms around each other, living room",
    "A person tying shoelaces on running shoes, both hands, close-up on the laces",
    "Hands typing on a mechanical keyboard with visible keycap legends, desk lamp lighting",
    "A waiter carrying a tray of drinks through a busy restaurant, one hand raised",
    "Close-up of hands kneading dough on a floured counter, bakery setting",
    "A guitarist's hands on the fretboard, fingers pressing strings, stage lighting",
    "Perfume bottle held between fingers against a marble background, embossed brand text "
    "on the glass",
]

CLEAN_PROMPTS = [
    "A single ceramic vase on a plain white background, soft studio lighting, product shot",
    "A folded stack of neutral linen towels on a wooden shelf, minimal styling",
    "An empty modern armchair in a sunlit room, wide shot, no people",
    "A bar of soap on a stone dish, plain background, soft shadow",
    "A pair of leather boots side by side on a concrete floor, no people",
    "A closed cardboard shipping box on a table, plain background",
    "A potted monstera plant against a plain wall, natural light",
    "A wristwatch lying flat on a dark slate surface, no hands, top-down",
    "A stack of three hardback books on a desk, spines plain, no text",
    "A glass of water on a wooden table, plain background, side lighting",
]


#: Image models are quota-tight; a batch will 429 without generous backoff.
MAX_ATTEMPTS = 5
BASE_BACKOFF_SECONDS = 20


async def generate(client: genai.Client, prompt: str, path: Path) -> bool:
    if path.exists():
        print(f"  {path.name}: already present, skipping")
        return True

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await client.aio.models.generate_content(model=MODEL, contents=prompt)
        except Exception as exc:  # noqa: BLE001 — one refusal must not stop the batch
            message = str(exc)
            if "RESOURCE_EXHAUSTED" in message and attempt < MAX_ATTEMPTS:
                delay = BASE_BACKOFF_SECONDS * attempt
                print(
                    f"  {path.name}: rate limited, retrying in {delay}s ({attempt}/{MAX_ATTEMPTS})"
                )
                await asyncio.sleep(delay)
                continue
            print(f"  {path.name}: FAILED ({message[:80]})")
            return False

        for candidate in response.candidates or []:
            for part in candidate.content.parts or []:
                blob = getattr(part, "inline_data", None)
                if blob and blob.data:
                    path.write_bytes(blob.data)
                    print(f"  {path.name}: {len(blob.data) // 1024}KB")
                    return True

        print(f"  {path.name}: no image returned")
        return False

    return False


async def main(count: int, out_dir: Path, concurrency: int) -> int:
    if not settings.use_vertex_ai and not settings.google_api_key:
        print("No Gemini credentials configured — see backend/.env.example")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    client = genai.Client()

    # Roughly two thirds defect-prone, one third clean, per the eval set target.
    clean_count = max(count // 3, 1)
    hard_count = count - clean_count

    jobs: list[tuple[str, Path]] = []
    for index in range(hard_count):
        prompt = HARD_PROMPTS[index % len(HARD_PROMPTS)]
        jobs.append((prompt, out_dir / f"hard_{index + 1:02d}.png"))
    for index in range(clean_count):
        prompt = CLEAN_PROMPTS[index % len(CLEAN_PROMPTS)]
        jobs.append((prompt, out_dir / f"clean_{index + 1:02d}.png"))

    print(f"generating {len(jobs)} candidates with {MODEL} into {out_dir}")
    semaphore = asyncio.Semaphore(concurrency)

    async def one(prompt: str, path: Path) -> bool:
        async with semaphore:
            return await generate(client, prompt, path)

    results = await asyncio.gather(*(one(prompt, path) for prompt, path in jobs))
    made = sum(1 for ok in results if ok)

    print(f"\n{made}/{len(jobs)} generated")
    print(
        "\nNext: open each image and write down the defects you can actually SEE.\n"
        "Do not label what the prompt asked for — label what is there. Files named\n"
        "clean_* are candidates for the clean set only if they really are clean."
    )
    return 0 if made else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--out", type=Path, default=Path("../eval/images"))
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    sys.exit(asyncio.run(main(args.count, args.out, args.concurrency)))
