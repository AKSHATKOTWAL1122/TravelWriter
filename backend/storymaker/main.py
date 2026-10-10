from fastapi import FastAPI

app = FastAPI(title="StoryMaker")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
