import json
import os
import shutil
import subprocess
import tempfile
from typing import Any


DEFAULT_MODEL = "inclusionai/ling-3.0-flash-fin:free"
DEFAULT_CONFIG_FILE = os.path.join("config", "hermes.json")
DEFAULT_MAX_TURNS = 8
DEFAULT_TIMEOUT_SECONDS = 420
DEFAULT_MAX_CANDIDATES = 3

ALLOWED_CATEGORIES = {
    "oil", "markets", "banks", "companies", "investment",
    "government", "real_estate", "employment", "technology",
    "tourism", "industry", "mining", "transport", "economy", "other",
}

ALLOWED_IMPACTS = {
    "positive", "negative", "neutral", "mixed", "unknown",
}

ALLOWED_TYPES = {
    "news", "analysis", "report", "data",
}


RESEARCH_SYSTEM_PROMPT = """
أنت طبقة البحث والتحقق المتقدمة لقناة Saudi Economy Daily.

المهمة ليست إعادة صياغة الخبر فقط. يجب أن تتعامل مع كل عنصر كقصة إخبارية تحتاج بحثاً إضافياً قبل نشرها.

قواعد البحث الإلزامية:
1. استخدم أداة web_search للبحث عن كل قصة مهمة في مصادر مستقلة متعددة.
2. ابدأ بالمصدر الأصلي الموجود في المادة، ثم ابحث عن مصدر رسمي أو أولي إن وجد، ثم مصدر اقتصادي مستقل أو وكالة أنباء موثوقة.
3. استخدم صيغ بحث متنوعة، بما فيها اسم الشركة/الجهة + الحدث + التاريخ، وsite:domain عند الحاجة.
4. عند توفر web_extract استخدمه لقراءة صفحات المصادر المهمة بدلاً من الاعتماد على عنوان البحث فقط. إذا لم تتوفر أداة استخراج، استخدم مقتطفات نتائج البحث والمحتوى المقدم في المادة ولا تدّعِ أنك قرأت الصفحة كاملة.
5. ابحث أيضاً عن أخبار أو بيانات سابقة مرتبطة بالقصة خلال الأيام أو الأسابيع السابقة عندما يساعد ذلك على تفسير التطور الحالي.
6. اربط الأخبار المرتبطة بالسياق، لكن لا تدمج قصتين مختلفتين في خبر واحد.
7. إذا وجدت مرشحين يغطون الحدث نفسه، اعتبر واحداً فقط هو القصة الأساسية وحدد بقية المرشحين كنسخ مكررة.
8. لا تنسب رقماً أو تاريخاً أو تصريحاً إلى مصدر ما لم تجده فعلاً في المادة أو نتيجة بحث مرتبطة بالمصدر.
9. عند اختلاف المصادر، لا تختر رقماً بالحدس؛ اعرض الاختلاف داخل الملخص أو خفّض درجة الثقة.
10. لا تختلق أسماء مصادر أو روابط. المصادر المساندة يجب أن تكون صفحات أو نتائج بحث وصلت إليها فعلاً.
11. لا تستخدم معلومات غير مرتبطة بالسعودية أو ذات أثر مباشر على الاقتصاد السعودي.
12. لا تحوّل الخبر إلى توصية استثمارية، ولا تقل للقارئ ماذا ينبغي أن يشتري أو يبيع.

طريقة كتابة النتيجة:
- الخبر النهائي يجب أن يكون خبراً واحداً مرتباً وغنياً بالمعلومات، وليس تقريراً طويلاً.
- العنوان واضح ومباشر بدون مبالغة.
- الملخص من 3 إلى 5 جمل قصيرة، ويضم أهم الحقائق والأرقام والتواريخ والسياق المرتبط الذي تم التحقق منه.
- أبرز المعلومات: 3 إلى 4 نقاط مؤكدة.
- الجهات المتأثرة: الشركات والجهات والقطاعات ذات العلاقة المباشرة.
- لماذا يهم؟ 2 إلى 3 جمل تشرح أهمية الحدث وتأثيره الاقتصادي المحتمل من دون الجزم بما لم تثبته المصادر.
- التأثير المحتمل يمكن أن يكون positive أو negative أو neutral أو mixed أو unknown.
- الأهمية ليست احتمالية الربح؛ هي أهمية الخبر لقارئ يهتم بالاقتصاد السعودي، وتقاس من 0 إلى 100.
- الثقة تعكس قوة الأدلة والمصادر واتساق الأرقام، وتقاس من 0 إلى 100.

الصدق أهم من الإكمال. عند نقص الأدلة، قل بوضوح إن المعلومة لم يتم التحقق منها ولا تخمن.

أعد JSON فقط، من دون Markdown ومن دون أي شرح خارج JSON، بالشكل:
{
  "results": [
    {
      "id": "article-id",
      "publish": true,
      "research_performed": true,
      "duplicate_of": null,
      "importance": 82,
      "confidence": 90,
      "content_type": "news",
      "category": "markets",
      "market_impact": "negative",
      "headline": "عنوان مختصر وواضح",
      "summary": "ملخص غني بالمعلومات من 3 إلى 5 جمل قصيرة.",
      "why_it_matters": "سبب أهمية الخبر وأثره المحتمل.",
      "affected_entities": ["جهة أو شركة"],
      "key_facts": ["معلومة أو رقم", "معلومة أو رقم", "معلومة أو رقم"],
      "supporting_sources": [
        {"name": "اسم المصدر", "url": "https://example.com/..."}
      ]
    }
  ]
}
"""


def load_config() -> dict[str, Any]:
    config: dict[str, Any] = {
        "model": DEFAULT_MODEL,
        "max_turns": DEFAULT_MAX_TURNS,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "max_candidates": DEFAULT_MAX_CANDIDATES,
        "web_backend": "firecrawl",
        "enabled": True,
        "fallback_to_legacy": True,
    }

    path = os.getenv("HERMES_CONFIG_FILE", DEFAULT_CONFIG_FILE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            config.update(raw)
    except (OSError, json.JSONDecodeError):
        pass

    env_map = {
        "model": "HERMES_MODEL",
        "max_turns": "HERMES_MAX_TURNS",
        "timeout_seconds": "HERMES_TIMEOUT_SECONDS",
        "max_candidates": "HERMES_MAX_CANDIDATES",
        "web_backend": "HERMES_WEB_BACKEND",
    }

    for key, env_key in env_map.items():
        value = os.getenv(env_key)
        if value not in (None, ""):
            config[key] = value

    for key in ("max_turns", "timeout_seconds", "max_candidates"):
        try:
            config[key] = int(config[key])
        except (TypeError, ValueError):
            config[key] = {
                "max_turns": DEFAULT_MAX_TURNS,
                "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
                "max_candidates": DEFAULT_MAX_CANDIDATES,
            }[key]

    mode = os.getenv("HERMES_ENABLED")
    if mode is not None:
        config["enabled"] = mode.strip().lower() not in {"0", "false", "no", "off"}

    fallback = os.getenv("HERMES_FALLBACK_TO_LEGACY")
    if fallback is not None:
        config["fallback_to_legacy"] = fallback.strip().lower() not in {"0", "false", "no", "off"}

    config["max_turns"] = max(1, min(20, int(config["max_turns"])))
    config["timeout_seconds"] = max(60, min(1200, int(config["timeout_seconds"])))
    config["max_candidates"] = max(1, min(10, int(config["max_candidates"])))
    config["model"] = str(config["model"]).strip() or DEFAULT_MODEL
    config["web_backend"] = str(config.get("web_backend", "")).strip()

    return config


def clean_json_text(text: str) -> str:
    if not text:
        return ""

    text = str(text).strip()
    for prefix in ("```json", "```JSON", "```"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break

    if text.endswith("```"):
        text = text[:-3]

    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        text = text[first:last + 1]

    return text.strip()


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_result(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    article_id = str(item.get("id", "")).strip()
    if not article_id:
        return None

    importance = max(0, min(100, _as_int(item.get("importance"), 0)))
    confidence = max(0, min(100, _as_int(item.get("confidence"), 0)))

    content_type = item.get("content_type", "news")
    if content_type not in ALLOWED_TYPES:
        content_type = "news"

    category = item.get("category", "other")
    if category not in ALLOWED_CATEGORIES:
        category = "other"

    impact = item.get("market_impact", "unknown")
    if impact not in ALLOWED_IMPACTS:
        impact = "unknown"

    research_performed = item.get("research_performed", False)
    if not isinstance(research_performed, bool):
        research_performed = False

    duplicate_of = item.get("duplicate_of")
    if duplicate_of in (None, "", False):
        duplicate_of = None
    else:
        duplicate_of = str(duplicate_of).strip() or None
        if duplicate_of == article_id:
            duplicate_of = None

    entities = item.get("affected_entities", [])
    facts = item.get("key_facts", [])
    supporting_sources = item.get("supporting_sources", [])

    if not isinstance(entities, list):
        entities = []
    if not isinstance(facts, list):
        facts = []
    if not isinstance(supporting_sources, list):
        supporting_sources = []

    entities = [str(x).strip() for x in entities if str(x).strip()][:6]
    facts = [str(x).strip() for x in facts if str(x).strip()][:4]

    normalized_sources = []
    for source in supporting_sources[:8]:
        if not isinstance(source, dict):
            continue
        name = str(source.get("name", "")).strip()
        url = str(source.get("url", "")).strip()
        if name and url.startswith(("http://", "https://")):
            normalized_sources.append({"name": name, "url": url})

    headline = str(item.get("headline", "")).strip()
    summary = str(item.get("summary", "")).strip()
    why = str(item.get("why_it_matters", "")).strip()

    publish = item.get("publish", False)
    if not isinstance(publish, bool):
        publish = False

    if not headline or not summary:
        publish = False

    return {
        "id": article_id,
        "publish": publish,
        "research_performed": research_performed,
        "duplicate_of": duplicate_of,
        "importance": importance,
        "confidence": confidence,
        "content_type": content_type,
        "category": category,
        "market_impact": impact,
        "headline": headline,
        "summary": summary,
        "why_it_matters": why,
        "affected_entities": entities,
        "key_facts": facts,
        "supporting_sources": normalized_sources,
    }


def parse_results(text: str) -> dict[str, dict[str, Any]]:
    payload = clean_json_text(text)
    if not payload:
        raise ValueError("Hermes returned an empty response")

    parsed = json.loads(payload)
    raw_results = parsed.get("results", []) if isinstance(parsed, dict) else []
    if not isinstance(raw_results, list):
        raise ValueError("Hermes JSON does not contain a results list")

    results = {}
    for item in raw_results:
        normalized = normalize_result(item)
        if normalized:
            results[normalized["id"]] = normalized
    return results


def find_hermes_binary() -> str | None:
    configured = os.getenv("HERMES_BINARY")
    if configured:
        if os.path.isfile(configured) and os.access(configured, os.X_OK):
            return configured
        found = shutil.which(configured)
        if found:
            return found

    for candidate in (
        "hermes",
        os.path.expanduser("~/.local/bin/hermes"),
        os.path.expanduser("~/.hermes/hermes-agent/.hermes/bin/hermes"),
    ):
        found = shutil.which(candidate) if os.path.basename(candidate) == candidate else candidate
        if found and os.path.isfile(found) and os.access(found, os.X_OK):
            return found

    return None


def build_prompt(articles: list[dict[str, Any]], sources: list[dict[str, Any]]) -> str:
    source_hints = []
    for source in sources:
        source_hints.append({
            "name": str(source.get("name", ""))[:120],
            "website": str(source.get("url", ""))[:250],
            "type": str(source.get("type", ""))[:80],
            "topics": source.get("topics", [])[:8] if isinstance(source.get("topics", []), list) else [],
        })

    prepared = []
    for article in articles:
        prepared.append({
            "id": str(article.get("id", "")),
            "title": str(article.get("title", ""))[:600],
            "source": str(article.get("source", ""))[:150],
            "source_type": str(article.get("source_type", ""))[:100],
            "url": str(article.get("url", ""))[:500],
            "published_at": str(article.get("published_at", ""))[:80],
            "content": str(article.get("content", ""))[:16000],
        })

    return f"""
{RESEARCH_SYSTEM_PROMPT}

المصادر الموجودة في النظام والتي ينبغي إعطاؤها أولوية عند البحث:
{json.dumps(source_hints, ensure_ascii=False, indent=2)}

القصص الحالية التي تحتاج إلى بحث عميق:
{json.dumps(prepared, ensure_ascii=False, indent=2)}

تعليمات إضافية:
- لا تكتفِ بقراءة النص المقدم. ابحث على الويب عن كل قصة قابلة للنشر.
- حاول تأكيد كل رقم مهم بمصدر أصلي أو مستقل.
- أضف المصادر المساندة التي استخدمتها فعلياً في البحث داخل supporting_sources.
- لا تغيّر id.
- لا تدمج قصتين مختلفتين لمجرد وجود صلة اقتصادية بينهما.
- إذا كان عنصران أو أكثر يصفون الحدث نفسه، اختر القصة الأساسية واملأ duplicate_of في النسخ الأخرى.
- لا تستخدم duplicate_of إلا عندما يكون الحدث نفسه فعلاً، وليس مجرد علاقة أو تشابه موضوعي.
- أعد نتيجة لكل id ما لم يتعذر عليك تحليلها بالكامل.
"""


def _write_runtime_config(config: dict[str, Any], home: str) -> None:
    os.makedirs(home, exist_ok=True)
    lines = [
        "model:",
        "  provider: openrouter",
        f"  default: {json.dumps(config['model'], ensure_ascii=False)}",
    ]

    if config.get("web_backend"):
        lines.extend([
            "web:",
            f"  backend: {json.dumps(config['web_backend'])}",
        ])

    with open(os.path.join(home, "config.yaml"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def research_articles(
    articles: list[dict[str, Any]],
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    config = load_config()

    if not config["enabled"]:
        print("Hermes research disabled by configuration.")
        return {}

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Hermes research unavailable: OPENROUTER_API_KEY is missing.")
        return {}

    if not articles:
        return {}

    binary = find_hermes_binary()
    if not binary:
        print("Hermes research unavailable: hermes executable was not found.")
        return {}

    limited_articles = articles[:config["max_candidates"]]
    prompt = build_prompt(limited_articles, sources or [])

    runtime_home = tempfile.mkdtemp(prefix="saudi-economy-hermes-")
    env = os.environ.copy()
    env["OPENROUTER_API_KEY"] = api_key
    env["HERMES_HOME"] = runtime_home

    _write_runtime_config(config, runtime_home)

    command = [
        binary,
        "chat",
        "--oneshot",
        "--query-file",
        "-",
        "--provider",
        "openrouter",
        "--model",
        config["model"],
        "--toolsets",
        "web",
        "--max-turns",
        str(config["max_turns"]),
    ]

    print("Starting Hermes deep research...")
    print(f"Hermes model: {config['model']}")
    print(f"Hermes candidates: {len(limited_articles)}")
    print(f"Hermes binary: {binary}")
    if config.get("web_backend"):
        print(f"Hermes web backend: {config['web_backend']}")
    else:
        print("Hermes web backend: auto-detect")

    try:
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=config["timeout_seconds"],
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("Hermes research timed out.")
        shutil.rmtree(runtime_home, ignore_errors=True)
        return {}
    except OSError as error:
        print(f"Hermes execution error: {error}")
        shutil.rmtree(runtime_home, ignore_errors=True)
        return {}

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

   if completed.returncode != 0:
    print(f"Hermes exit code: {completed.returncode}")
    print("===== HERMES STDERR =====")
    print(stderr[-10000:] if stderr else "(empty)")
    print("===== HERMES STDOUT =====")
    print(stdout[-10000:] if stdout else "(empty)")

        shutil.rmtree(runtime_home, ignore_errors=True)
        return {}

    if stderr:
        print(f"Hermes diagnostics: {stderr[-2000:]}")

    try:
        results = parse_results(stdout)
    except (ValueError, json.JSONDecodeError) as error:
        print(f"Hermes returned invalid JSON: {error}")
        print(stdout[:5000])
        shutil.rmtree(runtime_home, ignore_errors=True)
        return {}

    # Only accept results that explicitly report a research pass and include
    # at least one supporting source different from the original source.
    # This prevents a plain rewrite from silently replacing the legacy path.
    validated = {}
    original_by_id = {str(a.get("id", "")): str(a.get("source", "")).strip() for a in limited_articles}

    for article_id, result in results.items():
        if not result.get("research_performed"):
            continue

        primary = original_by_id.get(article_id, "").lower()
        independent_sources = []
        for source in result.get("supporting_sources", []):
            name = str(source.get("name", "")).strip()
            if name and name.lower() != primary and name.lower() not in {x.lower() for x in independent_sources}:
                independent_sources.append(name)

        if not independent_sources:
            continue

        validated[article_id] = result

    print(f"Hermes validated research results: {len(validated)}")

    shutil.rmtree(runtime_home, ignore_errors=True)

    return validated


def supporting_source_names(result: dict[str, Any], primary_source: str) -> list[str]:
    values = []
    primary = primary_source.strip().lower()
    for item in result.get("supporting_sources", []) if isinstance(result, dict) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name or name.lower() == primary or name in values:
            continue
        values.append(name)
        if len(values) >= 5:
            break
    return values
