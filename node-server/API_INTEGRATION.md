# Uniflux Marketplace — Frontend Integration Guide

## Base URL

| Environment | URL |
|---|---|
| Local | `http://localhost:3085` |
| Production | `https://your-cloud-run-url.run.app` |

---

## Public APIs (No Auth Required)

### 1. Get Jobs — Paginated

```
GET /api/v1/marketplace/jobs/public
```

**Query Parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `page` | number | `1` | Page number |
| `keyword` | string | - | Search by title / role / description. e.g. `java`, `react developer`, `devops` |
| `job_type` | string | - | `fulltime` / `parttime` / `contract` / `internship` / `temporary` |
| `location` | string | - | e.g. `new york`, `remote`, `california` |
| `site` | string | - | `indeed` / `linkedin` / `jsearch` / `glassdoor` |
| `skills` | string | - | Comma-separated. e.g. `python,aws,react` |

**Response:**
```json
{
  "total": 49781,
  "page": 1,
  "limit": 200,
  "total_pages": 249,
  "has_more": true,
  "jobs": [
    {
      "id": "684abc123def456",
      "source_site": "indeed",
      "title": "Java Developer",
      "company_name": "Google",
      "company_url": "https://google.com",
      "location": {
        "raw": "New York, NY",
        "city": "New York",
        "state": "NY",
        "country": "US",
        "is_remote": false
      },
      "salary": {
        "min": 80000,
        "max": 120000,
        "currency": "USD",
        "interval": "yearly",
        "source": "jsearch"
      },
      "job_type": "fulltime",
      "description": "Job description text...",
      "posted_at": "2026-06-10T00:00:00Z",
      "url": "https://job-apply-link.com",
      "skills": ["Java", "Spring Boot", "AWS"],
      "scraped_at": "2026-06-16T10:00:00Z"
    }
  ]
}
```

---

### 2. Get Counts & Filter Breakdown

```
GET /api/v1/marketplace/jobs/public/counts
```

Same filter params as above (`keyword`, `job_type`, `location`, `site`, `skills`). No `page`.

**Response:**
```json
{
  "total": 49781,
  "by_site": {
    "indeed": 35000,
    "linkedin": 10000,
    "jsearch": 4781
  },
  "by_job_type": {
    "fulltime": 38000,
    "contract": 7000,
    "parttime": 3000,
    "internship": 1781
  }
}
```

---

## Pagination

200 jobs per page. Use `page` param to navigate.

```
Page 1: GET /public?page=1
Page 2: GET /public?page=2
Page N: GET /public?page=N
```

Stop when `has_more: false` or `page >= total_pages`.

**Total pages formula:**
```js
totalPages = Math.ceil(total / 200)
```

---

## Filter Examples

```
# All jobs
GET /public?page=1

# By keyword / role
GET /public?page=1&keyword=java
GET /public?page=1&keyword=react developer
GET /public?page=1&keyword=devops
GET /public?page=1&keyword=cloud engineer
GET /public?page=1&keyword=python
GET /public?page=1&keyword=machine learning

# By job type
GET /public?page=1&job_type=fulltime
GET /public?page=1&job_type=contract
GET /public?page=1&job_type=parttime
GET /public?page=1&job_type=internship

# By location
GET /public?page=1&location=new york
GET /public?page=1&location=remote
GET /public?page=1&location=california
GET /public?page=1&location=texas

# By source site
GET /public?page=1&site=indeed
GET /public?page=1&site=linkedin
GET /public?page=1&site=jsearch

# By skills
GET /public?page=1&skills=python,aws
GET /public?page=1&skills=react,node,typescript

# Combined filters
GET /public?page=1&keyword=java&job_type=fulltime
GET /public?page=1&keyword=react&location=remote&job_type=fulltime
GET /public?page=1&keyword=devops&skills=aws,kubernetes&location=new york
GET /public?page=2&keyword=java&job_type=fulltime
```

---

## Recommended Frontend Flow

```
1. On page load:
   → GET /public/counts              → show total count, populate filter dropdowns
   → GET /public?page=1             → load first 200 jobs

2. User types keyword / applies filter:
   → GET /public/counts?keyword=java → update total count
   → GET /public?page=1&keyword=java → reset to page 1 with filter

3. User changes page:
   → GET /public?page=3&keyword=java → fetch page 3, keep filters

4. has_more=false → disable Next button
```

---

## Job Type Values (Normalized)

All job types are normalized — no matter what source returns:

| Stored as | Matches input |
|---|---|
| `fulltime` | Full-time, FULL-TIME, Full Time, full_time, Permanent |
| `parttime` | Part-time, PART-TIME, Part Time, part_time |
| `contract` | Contract, Contractor, C2C, W2, freelance |
| `contract_to_hire` | Contract to Hire, C2H |
| `internship` | Internship, Intern |
| `temporary` | Temporary, Temp |
| `perdiem` | Per Diem |

---

## Field Notes

| Field | Note |
|---|---|
| `job_type` | Always normalized — safe to filter/display |
| `skills` | May be empty `[]` for LinkedIn/Indeed jobs |
| `description` | May be `null` for some scraped jobs |
| `salary.min/max` | `null` when not available |
| `posted_at` | May be `null` — use `scraped_at` as fallback |
| `location.city/state` | May be `null` — use `location.raw` for display |
| All filters | Case-insensitive — `JAVA` = `java` = `Java` |

---

## Health Check

```
GET /health
```

Response:
```json
{
  "status": "ok",
  "service": "MARKETPLACE-SERVICE",
  "env": "development"
}
```
