"""Updates README.md with:
  1. Commit leaderboard (public repos ranked by my commits)  -> <!--LEADERBOARD:START--> ... <!--LEADERBOARD:END-->
  2. Accurate lifetime stats from GitHub GraphQL           -> <!--STATS:START--> ... <!--STATS:END-->
"""
import os
import re
import datetime as dt
import requests

USER = os.environ.get("GH_USER", "sadiqur199")
TOKEN = os.environ.get("GITHUB_TOKEN")
API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json"}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"

TOP_N = 10
MEDALS = ["🥇", "🥈", "🥉"]


def inject(content, start, end, text):
    pattern = re.compile(f"{re.escape(start)}.*?{re.escape(end)}", re.DOTALL)
    if not pattern.search(content):
        print(f"marker {start} not found in README, skipping")
        return content
    return pattern.sub(lambda _: f"{start}\n{text}\n{end}", content)


def bar(value, maximum, width=15):
    filled = round(width * value / maximum) if maximum else 0
    return "█" * filled + "░" * (width - filled)


# ---------------------------------------------------------------- leaderboard
def get_repos():
    repos, page = [], 1
    while True:
        r = requests.get(f"{API}/users/{USER}/repos", headers=HEADERS,
                         params={"per_page": 100, "page": page, "type": "owner"}, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    return [x for x in repos if not x["fork"]]


def commit_count(full_name):
    r = requests.get(f"{API}/repos/{full_name}/commits", headers=HEADERS,
                     params={"author": USER, "per_page": 1}, timeout=30)
    if r.status_code != 200:  # e.g. 409 for empty repos
        return 0
    m = re.search(r'[?&]page=(\d+)>; rel="last"', r.headers.get("Link", ""))
    return int(m.group(1)) if m else len(r.json())


def build_leaderboard():
    rows = []
    for repo in get_repos():
        c = commit_count(repo["full_name"])
        if c > 0:
            rows.append((repo["name"], c, repo["stargazers_count"], repo["language"] or "-"))
    rows.sort(key=lambda x: x[1], reverse=True)
    rows = rows[:TOP_N]
    if not rows:
        return "*No commits found yet.*"
    top = rows[0][1]
    lines = ["| Rank | Repository | Commits | Progress | ⭐ | Language |",
             "|:---:|---|:---:|---|:---:|---|"]
    for i, (name, c, stars, lang) in enumerate(rows, 1):
        rank = MEDALS[i - 1] if i <= 3 else f"#{i}"
        lines.append(f"| {rank} | [{name}](https://github.com/{USER}/{name}) | **{c}** | "
                     f"`{bar(c, top)}` | {stars} | {lang} |")
    lines += ["", f"<sub>Total commits in top {len(rows)} repos: **{sum(r[1] for r in rows):,}** · auto-updated by GitHub Actions</sub>"]
    return "\n".join(lines)


# ---------------------------------------------------------------- lifetime stats
def gql(query, variables):
    r = requests.post(f"{API}/graphql", json={"query": query, "variables": variables},
                      headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


YEAR_QUERY = """
query($login:String!,$from:DateTime!,$to:DateTime!){
  user(login:$login){
    contributionsCollection(from:$from,to:$to){
      totalCommitContributions
      restrictedContributionsCount
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      contributionCalendar{ totalContributions }
    }
  }
}"""


def build_stats():
    created = gql("query($l:String!){user(login:$l){createdAt}}", {"l": USER})["user"]["createdAt"]
    start_year = int(created[:4])
    now = dt.datetime.now(dt.timezone.utc)

    t = {"all": 0, "commits": 0, "private": 0, "prs": 0, "issues": 0, "reviews": 0}
    per_year = []
    for y in range(start_year, now.year + 1):
        frm = f"{y}-01-01T00:00:00Z"
        to = now.strftime("%Y-%m-%dT%H:%M:%SZ") if y == now.year else f"{y}-12-31T23:59:59Z"
        c = gql(YEAR_QUERY, {"login": USER, "from": frm, "to": to})["user"]["contributionsCollection"]
        total = c["contributionCalendar"]["totalContributions"]
        t["all"] += total
        t["commits"] += c["totalCommitContributions"]
        t["private"] += c["restrictedContributionsCount"]
        t["prs"] += c["totalPullRequestContributions"]
        t["issues"] += c["totalIssueContributions"]
        t["reviews"] += c["totalPullRequestReviewContributions"]
        per_year.append((y, total))

    lines = [
        "| 🏆 Total Contributions | 💻 Commits | 🔒 Private Contributions | 🔀 Pull Requests | 🐛 Issues | 👀 Code Reviews |",
        "|:---:|:---:|:---:|:---:|:---:|:---:|",
        f"| **{t['all']:,}** | **{t['commits']:,}** | **{t['private']:,}** | **{t['prs']:,}** | **{t['issues']:,}** | **{t['reviews']:,}** |",
        "",
        "**Contributions per year**",
        "",
        "```text",
    ]
    mx = max((n for _, n in per_year), default=0)
    for y, n in per_year:
        lines.append(f"{y}  {bar(n, mx, 24)}  {n:,}")
    lines += ["```", "", f"<sub>Lifetime numbers since {start_year} · auto-updated by GitHub Actions</sub>"]
    return "\n".join(lines)


def main():
    with open("README.md", encoding="utf-8") as f:
        content = f.read()

    try:
        content = inject(content, "<!--LEADERBOARD:START-->", "<!--LEADERBOARD:END-->", build_leaderboard())
    except Exception as e:
        print("leaderboard failed:", e)

    try:
        content = inject(content, "<!--STATS:START-->", "<!--STATS:END-->", build_stats())
    except Exception as e:
        print("stats failed:", e)

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    main()
