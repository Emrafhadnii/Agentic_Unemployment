from __future__ import annotations

import logging
import re
import time
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from agentic_unemployment.models.job import Job

log = logging.getLogger(__name__)

BASE_URL = "https://jobvision.ir"
API_URL = "https://candidateapi.jobvision.ir"
PAGE_SIZE = 30
_RETRY_STATUS = {429, 500, 502, 503, 504}


class JobVisionError(ValueError):
    pass


HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fa,en;q=0.8",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/jobs",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def make_client(
    transport: httpx.BaseTransport | None = None,
) -> httpx.Client:
    return httpx.Client(
        base_url=API_URL,
        headers=HEADERS,
        timeout=30.0,
        follow_redirects=True,
        transport=transport,
    )


def _request(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
    for attempt in range(1, 4):
        try:
            resp = client.request(method, url, **kwargs)
        except httpx.TransportError:
            if attempt == 3:
                raise
        else:
            if resp.status_code in _RETRY_STATUS:
                if attempt == 3:
                    resp.raise_for_status()
            else:
                resp.raise_for_status()
                return resp
        log.warning("jobvision retry %d/3 for %s", attempt, url)
        time.sleep(2.0 * attempt)
    raise AssertionError("unreachable")


def _unwrap(resp: httpx.Response) -> dict:
    try:
        payload = resp.json()
    except ValueError as e:
        raise JobVisionError("jobvision returned non-JSON") from e
    if not isinstance(payload, dict):
        raise JobVisionError("jobvision returned an unexpected payload")
    if payload.get("isSuccess") is False:
        message = payload.get("message") or "unknown error"
        raise JobVisionError(f"jobvision API error: {message}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise JobVisionError("jobvision response has no data object")
    return data


def _clean(value) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _label(value) -> str | None:
    if not isinstance(value, dict):
        return _clean(value)
    for key in ("titleFa", "title", "nameFa", "nameEn", "titleEn"):
        text = _clean(value.get(key))
        if text:
            return text
    return None


def _company(value) -> str | None:
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    if isinstance(name, dict):
        return _label(name)
    return _label(value)


def _location(value) -> str | None:
    if not isinstance(value, dict):
        return None
    parts: list[str] = []
    for key in ("province", "city", "region"):
        text = _label(value.get(key))
        if text and text not in parts:
            parts.append(text)
    return "، ".join(parts) or None


def _categories(value) -> str | None:
    if not isinstance(value, list):
        return None
    labels = [label for item in value if (label := _label(item))]
    return "، ".join(dict.fromkeys(labels)) or None


def _experience(value) -> str | None:
    if value is None:
        return None
    try:
        years = int(value)
    except (TypeError, ValueError):
        return _clean(value)
    if years <= 0:
        return "بدون نیاز به سابقه"
    return f"{years} سال"


def _education(value) -> str | None:
    if not isinstance(value, list):
        return None
    labels: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        degree = _label(item.get("degreeLevel"))
        field = _label(item.get("academicField"))
        label = " ".join(part for part in (degree, field) if part)
        if label:
            labels.append(label)
    return "، ".join(dict.fromkeys(labels)) or None


def _military(value) -> str | None:
    if value is True:
        return "نیاز به پایان خدمت"
    if value is False:
        return "بدون نیاز به پایان خدمت"
    return None


def _skills(data: dict) -> list[str]:
    values: list[str] = []
    for item in data.get("softwareRequirements") or []:
        if isinstance(item, dict) and (label := _label(item.get("software"))):
            values.append(label)
    for item in data.get("skills") or []:
        label = _label(item) if isinstance(item, dict) else _clean(item)
        if label:
            values.append(label)
    return list(dict.fromkeys(values))


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed


def _html_text(value) -> str | None:
    if not value:
        return None
    soup = BeautifulSoup(str(value), "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for li in soup.find_all("li"):
        li.insert(0, "• ")
        li.append("\n")
    for block in soup.find_all(["p", "div", "h1", "h2", "h3", "ul", "ol"]):
        block.append("\n")
    lines = [" ".join(line.split()) for line in soup.get_text().splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() or None


def parse_job(raw: dict, now: datetime) -> Job | None:
    job_id = raw.get("id")
    title = _clean(raw.get("title"))
    if job_id is None or title is None:
        return None

    properties = raw.get("properties") or {}
    activation = raw.get("activationTime") or {}
    return Job(
        source="jobvision",
        source_id=str(job_id),
        url=f"{BASE_URL}/jobs/{job_id}",
        title=title,
        company=_company(raw.get("company")),
        location_raw=_location(raw.get("location")),
        employment_type_raw=_label(raw.get("workType")),
        salary_raw=_label(raw.get("salary")),
        posted_raw=_clean(activation.get("beautifyFa")),
        posted_at=_parse_dt(activation.get("date")),
        fetched_at=now,
        is_remote=bool(properties.get("isRemote")),
        category_raw=_categories(raw.get("jobCategories")),
        experience_raw=_experience(properties.get("requiredRelatedExperienceYears")),
    )


def parse_list(payload: dict, now: datetime | None = None) -> list[Job]:
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise JobVisionError("jobvision list payload has no data object")
    posts = data.get("jobPosts") or []
    if not isinstance(posts, list):
        raise JobVisionError("jobvision list payload has no jobPosts list")

    stamp = now or datetime.now()
    jobs: list[Job] = []
    for raw in posts:
        if not isinstance(raw, dict):
            continue
        job = parse_job(raw, stamp)
        if job:
            jobs.append(job)
    return jobs


def parse_detail(payload: dict, job: Job) -> Job:
    data = payload.get("data", payload)
    if not isinstance(data, dict) or not data:
        raise JobVisionError(f"jobvision detail payload missing for {job.key}")

    if "description" in data:
        job.description = _html_text(data.get("description"))

    location = _location(data.get("location"))
    if location:
        job.location_raw = location
    employment = _label(data.get("workType"))
    if employment:
        job.employment_type_raw = employment
    if "isRemote" in data:
        job.is_remote = bool(data.get("isRemote"))

    salary = _label(data.get("salary"))
    if salary:
        job.salary_raw = salary
    categories = _categories(data.get("jobCategories"))
    if categories:
        job.category_raw = categories

    years = data.get("requiredRelatedExperienceYears")
    if years is not None:
        job.experience_raw = _experience(years)
    education = _education(data.get("academicRequirements"))
    if education:
        job.education_raw = education
    military = _military(data.get("shouldDoneMilitaryService"))
    if military:
        job.military_raw = military

    skills = _skills(data)
    if skills:
        job.skills = skills
    return job


def crawl_list(
    client: httpx.Client,
    keywords: list[str],
    remote: bool = False,
    max_pages: int = 5,
    delay: float = 1.5,
) -> list[Job]:
    query = " ".join(keyword.strip() for keyword in keywords if keyword.strip())
    stamp = datetime.now()
    seen: dict[str, Job] = {}

    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(delay)
        body = {
            "keyword": query,
            "requestedPage": page,
            "pageSize": PAGE_SIZE,
        }
        if remote:
            body["isRemote"] = True
        resp = _request(client, "POST", "/api/v1/JobPost/List", json=body)
        jobs = parse_list(_unwrap(resp), stamp)
        fresh = [job for job in jobs if job.source_id not in seen]
        log.info(
            "jobvision page %d: %d jobs, %d new in this crawl",
            page,
            len(jobs),
            len(fresh),
        )
        if not fresh:
            break
        for job in fresh:
            seen[job.source_id] = job
    return list(seen.values())


def crawl_details(client: httpx.Client, storage, delay: float = 1.5) -> tuple[int, int]:
    ok = failed = 0
    for job in storage.pending_detail(source="jobvision"):
        time.sleep(delay)
        try:
            resp = _request(
                client,
                "GET",
                "/api/v1/JobPost/Detail",
                params={"jobPostId": job.source_id},
            )
            storage.save_detail(parse_detail(_unwrap(resp), job))
            ok += 1
        except (httpx.HTTPError, JobVisionError) as e:
            failed += 1
            log.error("jobvision detail failed for %s: %s", job.key, e)
    return ok, failed
