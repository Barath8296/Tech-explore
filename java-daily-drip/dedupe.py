"""
No-repeat guard (free, no AI needed).

Compares a new topic against EVERYTHING sent before, not just exact matches:
  - same words in a different order        "HashMap internals" vs "Internals of HashMap"
  - extra fluff words                      "Virtual threads" vs "Java 21 virtual threads explained simply"
  - same underlying concept (CONCEPT key)  "Lightweight threads in Java" with concept "virtual threads"
"""

import re
from difflib import SequenceMatcher

STOP = set("""
a an the and or of in on for to with without from by at as is are be your you we our it its this that these
how why what when which who whom do does doing done vs versus using use used into about than then
day today new now whats what's s quick simple simply explained explain explaining
guide intro introduction beginner beginners basics basic tip tips trick tricks part deep dive understanding
understand learn learning lesson really actually every everyday finally meet hello world look first
""".split())

SYNONYMS = {
    "lightweight": "virtual", "loom": "virtual", "vthread": "virtual", "vthreads": "virtual",
    "db": "database", "databases": "database", "sql": "sql", "postgresql": "postgres",
    "k8s": "kubernetes", "auth": "authentication", "authn": "authentication", "authz": "authorization",
    "jwts": "jwt", "apis": "api", "rest": "rest", "restful": "rest", "hashmaps": "hashmap",
    "microservice": "microservices", "unittest": "unit", "junit5": "junit", "mockito": "mockito",
}


# common words that alone don't make two topics the same ("Spring Boot X" vs "Spring Boot Y")
GENERIC = {"java", "spring", "boot", "springboot", "backend", "api", "jdk", "code", "developer", "app",
           "application", "service", "system", "data", "release", "released", "feature", "update"}


def _stem(w):
    if w in GENERIC:
        return w
    for suf in ("ing", "ies", "es", "s"):
        if len(w) - len(suf) >= 4 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w[:-1] if len(w) > 4 and w.endswith("e") else w  # cache/caching -> cach


def tokens(text):
    words = re.findall(r"[a-z0-9+#]+", (text or "").lower())
    out = set()
    for w in words:
        if w in STOP or (len(w) < 2 and not w.isdigit()):
            continue
        w = SYNONYMS.get(w, w)
        out.add(_stem(w))
    return out


def similar(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    shared = ta & tb
    if not shared - GENERIC:  # only generic words in common -> different topics
        return False
    inter = len(shared)
    small = min(len(ta - GENERIC), len(tb - GENERIC))
    # all meaningful words of the shorter one appear in the longer one (e.g. concept inside a title)
    if small >= 2 and inter == small:
        return True
    if inter / len(ta | tb) >= 0.6:
        return True
    na, nb = " ".join(sorted(ta)), " ".join(sorted(tb))
    return SequenceMatcher(None, na, nb).ratio() >= 0.85


def is_repeat(candidates, history):
    """True if any of the candidate strings is similar to anything in history."""
    cands = [c for c in candidates if c and c.strip()]
    for h in history:
        for c in cands:
            if similar(c, h):
                return h
    return None


if __name__ == "__main__":  # quick self-check: python dedupe.py
    yes = [("Virtual threads", "Java 21 virtual threads explained simply"),
           ("HashMap internals", "Internals of HashMap"),
           ("Lightweight threads in Java", "Virtual threads"),
           ("The N+1 query problem", "N+1 query problem in JPA explained"),
           ("JWT tokens explained simply", "Understanding JWT tokens"),
           ("Spring Boot 4 released", "What's new in Spring Boot 4"),
           ("Netflix rebuilt its API gateway", "How Netflix rebuilt the API gateway")]
    no = [("HTTP methods: GET vs POST", "HTTP status codes you'll see every day"),
          ("@Component, @Service, @Repository", "Spring Data repositories"),
          ("Unit testing with JUnit 5", "@SpringBootTest and Testcontainers integration tests"),
          ("Lazy vs Eager loading", "Caching with @Cacheable"),
          ("Authentication vs Authorization", "How passwords should be stored (hashing with BCrypt)"),
          ("Spring Boot Actuator: health checks", "Spring profiles: dev, test and prod configs"),
          ("Your first Spring Boot app", "Spring Boot 4 released"),
          ("Java 25 released", "Spring Boot 4 released"),
          ("Spring Data repositories", "Spring Security filter chain")]
    bad = [p for p in yes if not similar(*p)] + [p for p in no if similar(*p)]
    print("dedupe self-check:", "OK" if not bad else f"FAILED {bad}")
