from __future__ import annotations

import uvicorn

from crewops_core import create_app

app = create_app()


def main() -> None:
    uvicorn.run("dashboard:app", host="0.0.0.0", port=8080, reload=False)


if __name__ == "__main__":
    main()
