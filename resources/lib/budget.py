"""How much of a capped source has been spent this month.

Some catalogues are free but small: TheGamesDB allows a thousand requests a
month on a public key, REG-Vault a thousand a day and asks not to be scraped
in bulk. Refusing to use them during a scan wastes them; using them without
counting empties the allowance on the first folder. So the spending is
counted, and a source steps aside for the rest of the period once its share
is gone.

The count is kept beside the caches, one file per provider, and is advisory:
a lost file costs a period's caution, nothing more.
"""
import json
import os
import time
from typing import Optional


def period(now: Optional[float] = None) -> str:
    """The month a request belongs to, as YYYY-MM."""
    return time.strftime("%Y-%m", time.gmtime(now if now is not None else time.time()))


class Budget:
    """What one provider may spend in a period, and what it has spent."""

    def __init__(self, folder: str, name: str, limit: int):
        self.folder = folder
        self.name = name
        self.limit = max(int(limit), 0)
        self._loaded: Optional[dict] = None

    @property
    def path(self) -> str:
        return os.path.join(self.folder, "{}.budget.json".format(self.name))

    def _state(self) -> dict:
        if self._loaded is None:
            state = {"period": period(), "spent": 0}
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    stored = json.load(handle)
                if isinstance(stored, dict) and stored.get("period") == state["period"]:
                    state["spent"] = int(stored.get("spent") or 0)
            except Exception:
                pass
            self._loaded = state
        return self._loaded

    def left(self) -> int:
        if self.limit <= 0:
            return 0
        return max(self.limit - self._state()["spent"], 0)

    def spend(self, amount: int = 1) -> None:
        state = self._state()
        state["spent"] += max(int(amount), 0)
        if not self.folder:
            return
        try:
            os.makedirs(self.folder, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(state, handle)
        except Exception:
            pass
