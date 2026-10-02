"""Fetch pictures for Kodi to keep in its art folder.

The links the library stores leave the person's sign-in out, and a source
may serve a picture only to someone signed in. So the scraper, which holds
the sign-in, fetches; each picture lands in the add-on's own folder and Kodi
moves it from there.
"""
import os
import uuid
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from . import net
from .providers import screenscraper

EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
              "image/gif": ".gif"}
#: Why a picture was not saved
MISSING = "missing"   # the source answered, and has no such picture
REFUSED = "refused"   # the source did not answer, or turned the request away


def save_one(url: str, folder: str, settings: Dict[str, Any],
             log: Callable[[str, bool], None]) -> Tuple[Optional[str], Optional[str]]:
    """The file a picture was written to, or None and why it was not."""
    try:
        response = net.get(screenscraper.signed_in(url, settings), log=log)
    except net.Error as err:
        log("saveart: {}".format(err), True)
        return None, MISSING if err.status == 404 else REFUSED
    kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
    extension = EXTENSIONS.get(kind)
    if extension is None or not response.body:
        # ScreenScraper answers a missing picture with the word NOMEDIA
        log("saveart: no picture from {}".format(net.safe_url(url)), True)
        return None, MISSING
    path = os.path.join(folder, uuid.uuid4().hex + extension)
    with open(path, "wb") as out:
        out.write(response.body)
    return path, None


def save(urls: Iterable[str], folder: str, settings: Dict[str, Any],
         log: Callable[[str, bool], None]) -> Dict[str, str]:
    """Each link that gave a picture, and the file it was written to."""
    os.makedirs(folder, exist_ok=True)
    files: Dict[str, str] = {}
    for url in urls:
        path, _ = save_one(url, folder, settings, log)
        if path is not None:
            files[url] = path
    return files
