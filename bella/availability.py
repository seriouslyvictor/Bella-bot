"""Official SENAI-SP availability source.

All knowledge of the listing pagination, VER TURMAS action, and class-details
HTML is contained here. Callers see only ``fetch_count() -> int``.
"""

import html
import logging
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

logger = logging.getLogger("bella")

COURSE_NAME = (
    "Inteligências Artificiais Generativas Aplicada a Programação - ChatGPT"
)
_PAGINATION_PATTERN = re.compile(r"GetQueryString\(\s*9\s*,\s*(\d+)")
_ACTION_PATTERN = re.compile(
    r"openModalTurmas\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*"
    r"(\d+)\s*,\s*(\d+)\s*,\s*'([^']+)'\s*,\s*"
    r"(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)"
)
# Captures (seat count, turma start date) per turma card. A second,
# simultaneously listed turma is a normal page state (the current class
# still running while the next one opens), not an anomaly, so callers use
# the paired start date to disambiguate rather than treating >1 match as a
# parse failure.
_TURMA_PATTERN = re.compile(
    r">\s*Vagas:\s*(\d+)\s*<.*?In[ií]cio<br\s*/?>\s*<strong>\s*"
    r"(\d{2}/\d{2}/\d{4})\s*<",
    re.IGNORECASE | re.DOTALL,
)


class AvailabilityError(RuntimeError):
    """The official source could not produce one trustworthy count."""


class AvailabilitySource(Protocol):
    async def fetch_count(self) -> int: ...

    async def close(self) -> None: ...


@dataclass(frozen=True)
class _VerTurmasAction:
    slug: str
    course_id: str
    school_id: str
    strategy: str
    scholarship: str
    free: str
    shift: str
    postgraduate: str


class SenaiAvailabilitySource:
    def __init__(
        self,
        listing_url: str,
        *,
        class_start: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._listing_url = listing_url
        # The Enrollment Card's current turma start date, used only to pick
        # the right turma when the class-details page lists more than one
        # (see _TURMA_PATTERN). Unused while exactly one turma is listed.
        self._class_start = class_start
        self._client = client or httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "BellaBot/1.0 SENAI availability check"},
        )
        self._owns_client = client is None

    async def fetch_count(self) -> int:
        try:
            return await self._fetch_count()
        except AvailabilityError as error:
            logger.warning("SENAI availability fetch failed: %s", error)
            raise
        except httpx.HTTPError as error:
            failure = AvailabilityError(
                f"request failed ({type(error).__name__})"
            )
            logger.warning("SENAI availability fetch failed: %s", failure)
            raise failure from error

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _fetch_count(self) -> int:
        first_page = await self._get_listing_page(self._listing_url)
        page_numbers = {
            int(match) for match in _PAGINATION_PATTERN.findall(first_page)
        }
        decoded = html.unescape(first_page)
        course_seen = COURSE_NAME in decoded
        action = _find_action(decoded)
        for page_number in sorted(page_numbers):
            if page_number <= 1 or action is not None:
                continue
            page = await self._get_listing_page(
                _with_query(self._listing_url, "pag", str(page_number))
            )
            decoded = html.unescape(page)
            course_seen = course_seen or COURSE_NAME in decoded
            action = _find_action(decoded)

        if action is None:
            reason = (
                "VER TURMAS target missing"
                if course_seen
                else "course row missing"
            )
            raise AvailabilityError(reason)

        response = await self._client.post(
            urljoin(self._listing_url, "/cursosturmas/"),
            data={
                "nomeCurso": action.slug,
                "cursoId": action.course_id,
                "escolaId": action.school_id,
                "estrategia": action.strategy,
                "bolsa": action.scholarship,
                "gratuito": action.free,
                "turno": action.shift,
                "pos": action.postgraduate,
            },
        )
        response.raise_for_status()
        turmas = _TURMA_PATTERN.findall(response.text)
        if not turmas:
            raise AvailabilityError("availability is unparseable")
        if len(turmas) == 1:
            return int(turmas[0][0])
        matches = [count for count, start in turmas if start == self._class_start]
        if len(matches) != 1:
            raise AvailabilityError(
                "availability is ambiguous: multiple turmas listed, "
                "none matched the Enrollment Card's class_start"
            )
        return int(matches[0])

    async def _get_listing_page(self, url: str) -> str:
        response = await self._client.get(url)
        response.raise_for_status()
        return response.text


def _find_action(page: str) -> _VerTurmasAction | None:
    for match in _ACTION_PATTERN.finditer(page):
        if match.group(1) != COURSE_NAME:
            continue
        return _VerTurmasAction(
            slug=match.group(2),
            course_id=match.group(3),
            school_id=match.group(4),
            strategy=match.group(5),
            scholarship=match.group(6),
            free=match.group(7),
            shift=match.group(8),
            postgraduate=match.group(9),
        )
    return None


def _with_query(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = value
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
