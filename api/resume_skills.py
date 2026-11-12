"""Canonical skill names and aliases for resume ontology matching.

ATS-style parsers (Greenhouse/Lever clones, SkillNER, spaCy EntityRuler) match
against a skill list rather than dumping raw resume text. Short/ambiguous tokens
like `go` and `c` are only accepted from a dedicated skills section.
"""

from __future__ import annotations

# canonical lowercase -> aliases (also lowercase). Canonical is always an alias of itself.
SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "python": ("python", "python3"),
    "go": ("golang", "go lang"),
    "rust": ("rust",),
    "java": ("java",),
    "kotlin": ("kotlin",),
    "scala": ("scala",),
    "c++": ("c++", "cpp", "cplusplus"),
    "c#": ("c#", "csharp", "c sharp"),
    "javascript": ("javascript", "ecmascript"),
    "typescript": ("typescript", "ts"),
    "node.js": ("node.js", "nodejs", "node"),
    "react": ("react", "reactjs", "react.js"),
    "vue": ("vue", "vuejs", "vue.js"),
    "angular": ("angular", "angularjs"),
    "next.js": ("next.js", "nextjs"),
    "django": ("django",),
    "flask": ("flask",),
    "fastapi": ("fastapi", "fast api"),
    "spring": ("spring", "spring boot", "springboot"),
    "ruby": ("ruby",),
    "rails": ("rails", "ruby on rails"),
    "php": ("php",),
    "swift": ("swift",),
    ".net": (".net", "dotnet", "asp.net"),
    "sql": ("sql",),
    "postgresql": ("postgresql", "postgres", "psql"),
    "mysql": ("mysql",),
    "sqlite": ("sqlite",),
    "mongodb": ("mongodb", "mongo"),
    "redis": ("redis",),
    "elasticsearch": ("elasticsearch", "elastic search", "opensearch"),
    "kafka": ("kafka", "apache kafka"),
    "rabbitmq": ("rabbitmq",),
    "graphql": ("graphql",),
    "grpc": ("grpc", "gRPC"),
    "rest": ("rest", "restful", "rest api"),
    "kubernetes": ("kubernetes", "k8s", "k8", "kube"),
    "docker": ("docker",),
    "helm": ("helm", "helm charts"),
    "terraform": ("terraform", "tf"),
    "ansible": ("ansible",),
    "puppet": ("puppet",),
    "chef": ("chef",),
    "pulumi": ("pulumi",),
    "aws": ("aws", "amazon web services"),
    "gcp": ("gcp", "google cloud", "google cloud platform"),
    "azure": ("azure", "microsoft azure"),
    "linux": ("linux", "gnu/linux"),
    "unix": ("unix",),
    "bash": ("bash", "shell scripting"),
    "git": ("git",),
    "github": ("github",),
    "gitlab": ("gitlab",),
    "github actions": ("github actions", "gh actions"),
    "gitlab ci": ("gitlab ci", "gitlab-ci"),
    "jenkins": ("jenkins",),
    "circleci": ("circleci", "circle ci"),
    "argocd": ("argocd", "argo cd", "argo"),
    "prometheus": ("prometheus",),
    "grafana": ("grafana",),
    "datadog": ("datadog",),
    "splunk": ("splunk",),
    "opentelemetry": ("opentelemetry", "otel", "open telemetry"),
    "istio": ("istio",),
    "envoy": ("envoy", "envoy proxy"),
    "nginx": ("nginx",),
    "ci/cd": ("ci/cd", "cicd", "ci cd", "continuous integration"),
    "sre": ("sre", "site reliability"),
    "devops": ("devops", "dev ops"),
    "platform engineering": ("platform engineering", "platform engineer"),
    "observability": ("observability",),
    "networking": ("networking",),
    "security": ("security", "infosec", "cybersecurity"),
    "iam": ("iam", "identity and access"),
    "oauth": ("oauth", "oauth2", "oauth 2"),
    "oidc": ("oidc", "openid connect"),
    "keycloak": ("keycloak",),
    "vault": ("vault", "hashicorp vault"),
    "consul": ("consul",),
    "nomad": ("nomad",),
    "packer": ("packer",),
    "vagrant": ("vagrant",),
    "vmware": ("vmware",),
    "openstack": ("openstack",),
    "lambda": ("lambda", "aws lambda"),
    "s3": ("s3", "amazon s3"),
    "ec2": ("ec2",),
    "eks": ("eks", "elastic kubernetes"),
    "ecs": ("ecs",),
    "gke": ("gke",),
    "aks": ("aks",),
    "cloudflare": ("cloudflare",),
    "nginx ingress": ("nginx ingress", "ingress-nginx"),
    "traefik": ("traefik",),
    "hadoop": ("hadoop",),
    "spark": ("spark", "apache spark"),
    "airflow": ("airflow", "apache airflow"),
    "dbt": ("dbt",),
    "snowflake": ("snowflake",),
    "bigquery": ("bigquery", "big query"),
    "redshift": ("redshift",),
    "pandas": ("pandas",),
    "numpy": ("numpy",),
    "pytorch": ("pytorch", "torch"),
    "tensorflow": ("tensorflow", "tf.keras"),
    "scikit-learn": ("scikit-learn", "sklearn", "scikit learn"),
    "llm": ("llm", "large language model", "llms"),
    "rag": ("rag", "retrieval augmented"),
    "machine learning": ("machine learning", "ml"),
    "html": ("html", "html5"),
    "css": ("css", "css3"),
    "tailwind": ("tailwind", "tailwindcss"),
    "jira": ("jira",),
    "confluence": ("confluence",),
    "agile": ("agile",),
    "scrum": ("scrum",),
}

# Short aliases that collide with English; only accept from a skills section.
AMBIGUOUS_ALIASES = frozenset({"go", "r", "c", "rest", "git"})

# Additional aliases that map to a canonical already listed.
_EXTRA_ALIASES: dict[str, str] = {
    "k8s": "kubernetes",
    "golang": "go",
    "postgres": "postgresql",
    "tf": "terraform",
    "nodejs": "node.js",
    "reactjs": "react",
}


def skill_patterns() -> list[tuple[str, str]]:
    """Return (canonical, alias) pairs, longest aliases first to avoid partial matches."""
    pairs: list[tuple[str, str]] = []
    for canonical, aliases in SKILL_ALIASES.items():
        seen = {canonical}
        pairs.append((canonical, canonical))
        for alias in aliases:
            alias_l = alias.lower()
            if alias_l not in seen:
                seen.add(alias_l)
                pairs.append((canonical, alias_l))
    for alias, canonical in _EXTRA_ALIASES.items():
        pairs.append((canonical, alias.lower()))
    pairs.sort(key=lambda item: len(item[1]), reverse=True)
    return pairs


_DISPLAY_OVERRIDES = {
    "c++": "C++",
    "c#": "C#",
    ".net": ".NET",
    "node.js": "Node.js",
    "next.js": "Next.js",
    "vue": "Vue",
    "aws": "AWS",
    "gcp": "GCP",
    "s3": "S3",
    "ec2": "EC2",
    "eks": "EKS",
    "ecs": "ECS",
    "gke": "GKE",
    "aks": "AKS",
    "iam": "IAM",
    "oauth": "OAuth",
    "oidc": "OIDC",
    "sre": "SRE",
    "ci/cd": "CI/CD",
    "llm": "LLM",
    "rag": "RAG",
    "sql": "SQL",
    "html": "HTML",
    "css": "CSS",
    "php": "PHP",
    "go": "Go",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "sqlite": "SQLite",
    "mongodb": "MongoDB",
    "graphql": "GraphQL",
    "grpc": "gRPC",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "github actions": "GitHub Actions",
    "gitlab ci": "GitLab CI",
    "github": "GitHub",
    "gitlab": "GitLab",
    "opentelemetry": "OpenTelemetry",
}


def default_display_name(canonical: str) -> str:
    key = canonical.strip().lower()
    if key in _DISPLAY_OVERRIDES:
        return _DISPLAY_OVERRIDES[key]
    return " ".join(part.upper() if part in {"ai", "ml", "dbt"} else part.capitalize() for part in key.split())
    """Return (canonical, alias) pairs, longest aliases first to avoid partial matches."""
    pairs: list[tuple[str, str]] = []
    for canonical, aliases in SKILL_ALIASES.items():
        seen = {canonical}
        pairs.append((canonical, canonical))
        for alias in aliases:
            alias_l = alias.lower()
            if alias_l not in seen:
                seen.add(alias_l)
                pairs.append((canonical, alias_l))
    for alias, canonical in _EXTRA_ALIASES.items():
        pairs.append((canonical, alias.lower()))
    pairs.sort(key=lambda item: len(item[1]), reverse=True)
    return pairs
