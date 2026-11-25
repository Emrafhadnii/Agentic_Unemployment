from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup, Tag

from agentic_unemployment.models.job import Job

log = logging.getLogger(__name__)
BASE_URL = "https://jobinja.ir/jobs"

CATEGORY_WEB_DEV = "وب،\u200c برنامه\u200cنویسی و نرم\u200cافزار"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fa,en;q=0.8",
}


def make_client() -> httpx.Client:
    return httpx.Client(headers=HEADERS, timeout=20.0, follow_redirects=True)


JOB_HREF = re.compile(r"/companies/([^/]+)/jobs/([^/?#]+)/")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_SALARY_HIDDEN = "برای مشاهده حقوق وارد شوید"
_UNITS = {"دقیقه": "minutes", "ساعت": "hours", "روز": "days", "هفته": "weeks"}


def _text(node: Tag | None) -> str | None:
    if node is None:
        return None
    s = " ".join(node.get_text(" ", strip=True).split())
    return s or None


def _canonical(href: str) -> str:
    p = urlsplit(href)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def _parse_relative(raw: str | None, now: datetime) -> datetime | None:
    if not raw:
        return None
    s = raw.translate(_DIGITS)
    if "امروز" in s:
        return now
    if "دیروز" in s:
        return now - timedelta(days=1)
    m = re.search(r"(\d+)\s*(دقیقه|ساعت|روز|هفته)", s)
    if m:
        return now - timedelta(**{_UNITS[m.group(2)]: int(m.group(1))})
    return None


def _meta_by_icon(card: Tag, icon: str) -> Tag | None:
    i = card.select_one(f"li.c-jobListView__metaItem i.c-icon--{icon}")
    return i.parent if i else None


def parse_card(card: Tag, now: datetime) -> Job | None:
    link = card.select_one("a.c-jobListView__titleLink")
    if link is None:
        return None
    m = JOB_HREF.search(link["href"])
    if not m:
        return None

    posted_raw = _text(card.select_one("span.c-jobListView__passedDays"))
    if posted_raw:
        posted_raw = posted_raw.strip("() ")

    company_li = _meta_by_icon(card, "construction")
    place_li = _meta_by_icon(card, "place")
    resume_li = _meta_by_icon(card, "resume")

    employment_raw, salary_raw = None, None
    if resume_li is not None:
        outer = resume_li.find("span", recursive=False)
        inner = outer.find("span", recursive=False) if outer else None
        employment_raw = _text(inner)
        full = _text(outer) or ""
        rest = full.replace(employment_raw or "", "", 1).strip()
        if rest and _SALARY_HIDDEN not in rest:
            salary_raw = rest

    return Job(
        source="jobinja",
        source_id=m.group(2),
        url=_canonical(link["href"]),
        title=_text(link),
        company=_text(company_li.find("span")) if company_li else None,
        location_raw=_text(place_li.find("span")) if place_li else None,
        employment_type_raw=employment_raw,
        is_remote="دورکاری" in (employment_raw or ""),
        salary_raw=salary_raw,
        posted_raw=posted_raw,
        posted_at=_parse_relative(posted_raw, now),
        fetched_at=now,
    )


def parse_list(html: str, now: datetime | None = None) -> list[Job]:
    now = now or datetime.now()
    soup = BeautifulSoup(html, "html.parser")
    jobs: dict[str, Job] = {}
    for card in soup.select("li.c-jobListView__item"):
        job = parse_card(card, now)
        if job:
            jobs.setdefault(job.source_id, job)
    return list(jobs.values())


def _norm_label(s: str) -> str:
    return re.sub(r"[\s\u200c\u200d]+", "", s)


_DETAIL_FIELDS = {
    _norm_label("دسته‌بندی شغلی"): "category_raw",
    _norm_label("موقعیت مکانی"): "location_raw",
    _norm_label("نوع همکاری"): "employment_type_raw",
    _norm_label("حداقل سابقه کار"): "experience_raw",
    _norm_label("حقوق"): "salary_raw",
    _norm_label("حداقل مدرک تحصیلی"): "education_raw",
    _norm_label("وضعیت نظام وظیفه"): "military_raw",
}
_SKILLS_LABEL = _norm_label("مهارت‌های مورد نیاز")


def _description_text(desc: Tag) -> str:
    for ad in desc.select("a.no-desc-display"):
        ad.decompose()
    for br in desc.find_all("br"):
        br.replace_with("\n")
    for li in desc.find_all("li"):
        li.insert(0, "• ")
        li.append("\n")
    for block in desc.find_all(["div", "h1", "ul", "p"]):
        block.append("\n")
    text = desc.get_text()
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def parse_detail(html: str, job: Job) -> Job:
    """Fill the detail-only fields of `job` from its detail page."""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one("section.c-jobView")
    if root is None:
        raise ValueError(f"detail layout not recognised for {job.key}")

    for li in root.select("li.c-infoBox__item"):
        h4 = li.select_one("h4.c-infoBox__itemTitle")
        if h4 is None:
            continue
        label = _norm_label(h4.get_text())
        tags = [t for t in (_text(s) for s in li.select("div.tags span")) if t]
        if label == _SKILLS_LABEL:
            job.skills = tags
        elif label in _DETAIL_FIELDS and tags:
            setattr(job, _DETAIL_FIELDS[label], "، ".join(tags))

    if job.location_raw:
        job.location_raw = job.location_raw.replace(" ،", "،")
    if job.employment_type_raw and "دورکاری" in job.employment_type_raw:
        job.is_remote = True

    desc = root.select_one("div.s-jobDesc")
    job.description = _description_text(desc) if desc else None
    return job


def build_search_url(
    keywords: list[str],
    category: str = CATEGORY_WEB_DEV,
    remote: bool = False,
    page: int = 1,
    preferred_before: int | None = None,
) -> str:
    params: list[tuple[str, str | int]] = [("filters[job_categories][0]", category)]
    params += [(f"filters[keywords][{i}]", kw) for i, kw in enumerate(keywords)]
    if remote:
        params.append(("filters[remote]", 1))
    params += [
        ("preferred_before", preferred_before or int(time.time())),
        ("sort_by", "relevance_desc"),
    ]
    if page > 1:
        params.append(("page", page))
    return f"{BASE_URL}?{urlencode(params)}"


_RETRY_STATUS = {429, 500, 502, 503, 504}


def get_with_retry(
    client: httpx.Client, url: str, retries: int = 3, backoff: float = 2.0
) -> httpx.Response:
    for attempt in range(1, retries + 1):
        try:
            resp = client.get(url)
            if resp.status_code in _RETRY_STATUS:
                raise httpx.HTTPStatusError(
                    f"status {resp.status_code}", request=resp.request, response=resp
                )
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in _RETRY_STATUS or attempt == retries:
                raise
        except httpx.TransportError:
            if attempt == retries:
                raise
        log.warning("retry %d/%d for %s", attempt, retries, url)
        time.sleep(backoff * attempt)
    raise AssertionError("unreachable")


def crawl_list(
    client: httpx.Client,
    keywords: list[str],
    remote: bool = False,
    max_pages: int = 5,
    delay: float = 1.5,
) -> list[Job]:
    stamp = int(time.time())
    seen: dict[str, Job] = {}
    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(delay)
        url = build_search_url(
            keywords, remote=remote, page=page, preferred_before=stamp
        )
        jobs = parse_list(get_with_retry(client, url).text)
        fresh = [j for j in jobs if j.source_id not in seen]
        log.info("page %d: %d jobs, %d new in this crawl", page, len(jobs), len(fresh))
        if not fresh:
            break
        for j in fresh:
            seen[j.source_id] = j
    return list(seen.values())


def crawl_details(client: httpx.Client, storage, delay: float = 1.5) -> tuple[int, int]:
    """Fetch the detail page of every pending job. Returns (ok, failed)."""
    ok = failed = 0
    for job in storage.pending_detail(source="jobinja"):
        time.sleep(delay)
        try:
            html = get_with_retry(client, job.url).text
            storage.save_detail(parse_detail(html, job))
            ok += 1
        except (httpx.HTTPError, ValueError) as e:
            failed += 1
            log.error("detail failed for %s: %s", job.key, e)
    return ok, failed
