# src/llm_regress/server/main.py
from __future__ import annotations


def run() -> None:
    import uvicorn

    from .app import create_app

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
