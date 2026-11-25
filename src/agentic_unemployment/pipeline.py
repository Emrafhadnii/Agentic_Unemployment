from __future__ import annotations

import logging
from dataclasses import dataclass

from agentic_unemployment.candidate import Candidate
from agentic_unemployment.config import SearchSpec
from agentic_unemployment.llm import LLMClient, LLMError
from agentic_unemployment.matcher import score_job
from agentic_unemployment.sources import SOURCES

log = logging.getLogger(__name__)


@dataclass
class CrawlStats:
    searches: int = 0
    search_failures: int = 0
    found: int = 0
    new: int = 0
    details_ok: int = 0
    details_failed: int = 0


def crawl_searches(
    db,
    searches: list[SearchSpec],
    *,
    max_pages: int = 5,
    delay: float = 1.5,
    fetch_details: bool = True,
) -> CrawlStats:
    """Crawl every search spec, store new jobs, then fill pending details."""
    stats = CrawlStats()
    grouped: dict[str, list[SearchSpec]] = {}
    for search in searches:
        grouped.setdefault(search.source, []).append(search)

    for source, specs in grouped.items():
        stats.searches += len(specs)
        module = SOURCES.get(source)
        if module is None:
            stats.search_failures += len(specs)
            log.error("unknown source %s", source)
            continue

        try:
            client = module.make_client()
        except Exception:
            stats.search_failures += len(specs)
            log.exception("cannot create client for source %s", source)
            continue

        with client:
            for search in specs:
                try:
                    jobs = module.crawl_list(
                        client,
                        search.keywords,
                        remote=search.remote,
                        max_pages=max_pages,
                        delay=delay,
                    )
                except Exception:
                    stats.search_failures += 1
                    log.exception(
                        "search %s source=%s remote=%s failed",
                        search.keywords,
                        source,
                        search.remote,
                    )
                    continue
                new = db.insert_new(jobs)
                stats.found += len(jobs)
                stats.new += len(new)
                log.info(
                    "source=%s search=%s remote=%s: %d found, %d new",
                    source,
                    search.keywords,
                    search.remote,
                    len(jobs),
                    len(new),
                )

    if fetch_details:
        stats.details_ok, stats.details_failed = crawl_pending_details(db, delay=delay)
    return stats


def crawl_pending_details(
    db, *, delay: float = 1.5, sources: list[str] | None = None
) -> tuple[int, int]:
    total_ok = total_failed = 0
    for source in sources or list(SOURCES):
        module = SOURCES.get(source)
        if module is None:
            log.error("unknown source %s", source)
            total_failed += 1
            continue
        if not db.count_pending_detail(source):
            continue
        try:
            with module.make_client() as client:
                ok, failed = module.crawl_details(client, db, delay=delay)
        except Exception:
            log.exception("detail crawl failed for source %s", source)
            total_failed += 1
            continue
        total_ok += ok
        total_failed += failed
    return total_ok, total_failed


def score_pending(
    db,
    llm: LLMClient,
    candidate: Candidate,
    limit: int = 50,
    max_attempts: int = 3,
    max_transient_in_row: int = 3,
) -> tuple[int, int, bool]:
    """Score unscored jobs. Returns (scored, failed, aborted)."""
    jobs = db.pending_match(candidate.hash, limit, max_attempts)
    ok = failed = streak = 0
    aborted = False

    for job in jobs:
        try:
            result = score_job(llm, candidate, job)
        except LLMError as e:
            if e.transient:
                streak += 1
                log.warning(
                    "transient LLM error on %s (%d in a row): %s", job.key, streak, e
                )
                if streak >= max_transient_in_row:
                    log.error("LLM unreachable, stopping; unscored jobs stay pending")
                    aborted = True
                    break
                continue
            db.record_match_failure(job.key, candidate.hash, str(e))
            failed += 1
            streak = 0
            log.error("scoring failed for %s: %s", job.key, e)
            continue
        except (
            ValueError
        ) as e:  # bad JSON or failed validation (pydantic errors are ValueErrors)
            db.record_match_failure(job.key, candidate.hash, str(e))
            failed += 1
            streak = 0
            log.error("unparseable output for %s: %s", job.key, e)
            continue
        except Exception:  # last resort: one broken job must never kill the run
            db.record_match_failure(job.key, candidate.hash, "unexpected scoring error")
            failed += 1
            streak = 0
            log.exception("unexpected error while scoring %s", job.key)
            continue

        streak = 0
        db.save_match(job.key, candidate.hash, llm.model, result)
        ok += 1
        log.info("[%3d] %-10s %s", result.score, result.verdict, job.title)

    return ok, failed, aborted
