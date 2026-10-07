import json
import os
import hashlib
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any


DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_CONFIG_FILE = os.path.join("config", "hermes.json")
DEFAULT_MAX_TURNS = 8
DEFAULT_TIMEOUT_SECONDS = 420
DEFAULT_MAX_CANDIDATES = 8
DEFAULT_DISCOVERY_LIMIT = 12
DEFAULT_DISCOVERY_TURNS = 10

ALLOWED_CATEGORIES = {
    "oil",
    "markets",
    "banks",
    "companies",
    "investment",
    "government",
    "real_estate",
    "employment",
    "technology",
    "tourism",
    "industry",
    "mining",
    "transport",
    "economy",
    "other",
}

ALLOWED_IMPACTS = {
    "positive",
    "negative",
    "neutral",
    "mixed",
    "unknown",
}

ALLOWED_TYPES = {
    "news",
    "analysis",
    "report",
    "data",
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
        "provider": "gemini",
        "max_turns": DEFAULT_MAX_TURNS,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "max_candidates": DEFAULT_MAX_CANDIDATES,
        "discovery_limit": DEFAULT_DISCOVERY_LIMIT,
        "discovery_turns": DEFAULT_DISCOVERY_TURNS,
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
        "provider": "HERMES_PROVIDER",
        "max_turns": "HERMES_MAX_TURNS",
        "timeout_seconds": "HERMES_TIMEOUT_SECONDS",
        "max_candidates": "HERMES_MAX_CANDIDATES",
        "discovery_limit": "HERMES_DISCOVERY_LIMIT",
        "discovery_turns": "HERMES_DISCOVERY_TURNS",
        "web_backend": "HERMES_WEB_BACKEND",
    }

    for key, env_key in env_map.items():
        value = os.getenv(env_key)

        if value not in (None, ""):
            config[key] = value

    for key in ("max_turns", "timeout_seconds", "max_candidates", "discovery_limit", "discovery_turns"):
        try:
            config[key] = int(config[key])
        except (TypeError, ValueError):
            config[key] = {
                "max_turns": DEFAULT_MAX_TURNS,
                "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
                "max_candidates": DEFAULT_MAX_CANDIDATES,
                "discovery_limit": DEFAULT_DISCOVERY_LIMIT,
                "discovery_turns": DEFAULT_DISCOVERY_TURNS,
            }[key]

    mode = os.getenv("HERMES_ENABLED")

    if mode is not None:
        config["enabled"] = (
            mode.strip().lower()
            not in {"0", "false", "no", "off"}
        )

    fallback = os.getenv("HERMES_FALLBACK_TO_LEGACY")

    if fallback is not None:
        config["fallback_to_legacy"] = (
            fallback.strip().lower()
            not in {"0", "false", "no", "off"}
        )

    config["max_turns"] = max(
        1,
        min(20, int(config["max_turns"]))
    )

    config["timeout_seconds"] = max(
        60,
        min(1200, int(config["timeout_seconds"]))
    )

    config["max_candidates"] = max(
        1,
        min(20, int(config["max_candidates"]))
    )

    config["discovery_limit"] = max(
        4,
        min(20, int(config["discovery_limit"]))
    )

    config["discovery_turns"] = max(
        4,
        min(20, int(config["discovery_turns"]))
    )

    config["model"] = (
        str(config["model"]).strip()
        or DEFAULT_MODEL
    )

    config["provider"] = (
        str(config.get("provider", "gemini")).strip()
        or "gemini"
    )

    config["web_backend"] = str(
        config.get("web_backend", "")
    ).strip()

    return config


def clean_json_text(text: str) -> str:
    """
    Extract the JSON object from Hermes output.

    Hermes may print:
    - progress messages
    - reasoning
    - tool output
    - the final JSON
    - additional terminal output

    Therefore we locate the first JSON object and the last closing brace.
    """

    if not text:
        return ""

    text = str(text).strip()

    # Remove common Markdown code fences.
    for prefix in (
        "```json",
        "```JSON",
        "```",
    ):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break

    if text.endswith("```"):
        text = text[:-3]

    text = text.strip()

    # First attempt: direct JSON parsing.
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # Find the first JSON object.
    first = text.find("{")

    # Find the last closing brace.
    last = text.rfind("}")

    if first != -1 and last != -1 and last > first:
        candidate = text[first:last + 1].strip()

        # Verify that the extracted candidate is actually JSON.
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    return text


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

    importance = max(
        0,
        min(
            100,
            _as_int(item.get("importance"), 0)
        ),
    )

    confidence = max(
        0,
        min(
            100,
            _as_int(item.get("confidence"), 0)
        ),
    )

    content_type = item.get(
        "content_type",
        "news",
    )

    if content_type not in ALLOWED_TYPES:
        content_type = "news"

    category = item.get(
        "category",
        "other",
    )

    if category not in ALLOWED_CATEGORIES:
        category = "other"

    impact = item.get(
        "market_impact",
        "unknown",
    )

    if impact not in ALLOWED_IMPACTS:
        impact = "unknown"

    research_performed = item.get(
        "research_performed",
        False,
    )

    if not isinstance(research_performed, bool):
        research_performed = False

    duplicate_of = item.get("duplicate_of")

    if duplicate_of in (
        None,
        "",
        False,
    ):
        duplicate_of = None
    else:
        duplicate_of = str(
            duplicate_of
        ).strip() or None

        if duplicate_of == article_id:
            duplicate_of = None

    entities = item.get(
        "affected_entities",
        [],
    )

    facts = item.get(
        "key_facts",
        [],
    )

    supporting_sources = item.get(
        "supporting_sources",
        [],
    )

    if not isinstance(entities, list):
        entities = []

    if not isinstance(facts, list):
        facts = []

    if not isinstance(supporting_sources, list):
        supporting_sources = []

    entities = [
        str(x).strip()
        for x in entities
        if str(x).strip()
    ][:6]

    facts = [
        str(x).strip()
        for x in facts
        if str(x).strip()
    ][:4]

    normalized_sources = []

    for source in supporting_sources[:8]:

        if not isinstance(source, dict):
            continue

        name = str(
            source.get("name", "")
        ).strip()

        url = str(
            source.get("url", "")
        ).strip()

        if (
            name
            and url.startswith(
                ("http://", "https://")
            )
        ):
            normalized_sources.append(
                {
                    "name": name,
                    "url": url,
                }
            )

    headline = str(
        item.get("headline", "")
    ).strip()

    summary = str(
        item.get("summary", "")
    ).strip()

    why = str(
        item.get("why_it_matters", "")
    ).strip()

    publish = item.get(
        "publish",
        False,
    )

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
        raise ValueError(
            "Hermes returned an empty response"
        )

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Hermes returned invalid JSON: {error}"
        ) from error

    raw_results = (
        parsed.get("results", [])
        if isinstance(parsed, dict)
        else []
    )

    if not isinstance(raw_results, list):
        raise ValueError(
            "Hermes JSON does not contain a results list"
        )

    results = {}

    for item in raw_results:
        normalized = normalize_result(item)

        if normalized:
            results[normalized["id"]] = normalized

    return results


def find_hermes_binary() -> str | None:
    configured = os.getenv(
        "HERMES_BINARY"
    )

    if configured:

        if (
            os.path.isfile(configured)
            and os.access(
                configured,
                os.X_OK,
            )
        ):
            return configured

        found = shutil.which(configured)

        if found:
            return found

    for candidate in (
        "hermes",
        os.path.expanduser(
            "~/.local/bin/hermes"
        ),
        os.path.expanduser(
            "~/.hermes/hermes-agent/.hermes/bin/hermes"
        ),
    ):

        found = (
            shutil.which(candidate)
            if os.path.basename(candidate)
            == candidate
            else candidate
        )

        if (
            found
            and os.path.isfile(found)
            and os.access(found, os.X_OK)
        ):
            return found

    return None


def build_prompt(
    articles: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> str:

    source_hints = []

    for source in sources:

        source_hints.append(
            {
                "name": str(
                    source.get("name", "")
                )[:120],
                "website": str(
                    source.get("url", "")
                )[:250],
                "type": str(
                    source.get("type", "")
                )[:80],
                "topics": (
                    source.get("topics", [])[:8]
                    if isinstance(
                        source.get("topics", []),
                        list,
                    )
                    else []
                ),
            }
        )

    prepared = []

    for article in articles:

        prepared.append(
            {
                "id": str(
                    article.get("id", "")
                ),
                "title": str(
                    article.get("title", "")
                )[:600],
                "source": str(
                    article.get("source", "")
                )[:150],
                "source_type": str(
                    article.get("source_type", "")
                )[:100],
                "url": str(
                    article.get("url", "")
                )[:500],
                "published_at": str(
                    article.get("published_at", "")
                )[:80],
                "content": str(
                    article.get("content", "")
                )[:16000],
            }
        )

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

مهم جداً:
يجب أن يكون آخر جزء من إجابتك JSON صالحاً فقط بالشكل المطلوب أعلاه.
لا تضع أي JSON إضافي بعده.
"""


def _write_runtime_config(
    config: dict[str, Any],
    home: str,
) -> None:

    os.makedirs(
        home,
        exist_ok=True,
    )

    lines = [
        "model:",
        f"  provider: {json.dumps(config.get('provider', 'gemini'))}",
        f"  default: {json.dumps(config['model'], ensure_ascii=False)}",
    ]

    if config.get("web_backend"):

        lines.extend(
            [
                "web:",
                f"  backend: {json.dumps(config['web_backend'])}",
            ]
        )

    with open(
        os.path.join(
            home,
            "config.yaml",
        ),
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            "\n".join(lines) + "\n"
        )


def _extract_json_from_output(
    stdout: str,
) -> str:
    """
    Hermes can print progress messages and tool information
    before/after the actual model answer.

    This function extracts the final JSON object safely.
    """

    if not stdout:
        return ""

    text = stdout.strip()

    # First, try the whole output.
    try:
        parsed = json.loads(text)

        if isinstance(parsed, dict):
            return json.dumps(
                parsed,
                ensure_ascii=False,
            )

    except json.JSONDecodeError:
        pass

    # Remove Markdown fences if present.
    text = text.replace(
        "```json",
        "",
    )

    text = text.replace(
        "```JSON",
        "",
    )

    text = text.replace(
        "```",
        "",
    )

    text = text.strip()

    # Locate all possible JSON object starts.
    positions = []

    start = 0

    while True:

        position = text.find(
            "{",
            start,
        )

        if position == -1:
            break

        positions.append(position)
        start = position + 1

    # Try every possible JSON object from the end.
    # This is useful when Hermes printed an earlier JSON-like object
    # and the final answer appears later.
    for first in reversed(positions):

        candidate = text[first:]

        # Try progressively shorter endings.
        last = len(candidate)

        while last > 0:

            closing = candidate.rfind(
                "}",
                0,
                last,
            )

            if closing == -1:
                break

            possible = candidate[
                :closing + 1
            ].strip()

            try:
                parsed = json.loads(
                    possible
                )

                if isinstance(parsed, dict):
                    if "results" in parsed:
                        return json.dumps(
                            parsed,
                            ensure_ascii=False,
                        )

            except json.JSONDecodeError:
                pass

            last = closing

    # Fallback to first/last brace extraction.
    first = text.find("{")
    last = text.rfind("}")

    if (
        first != -1
        and last != -1
        and last > first
    ):
        return text[
            first:last + 1
        ].strip()

    return text


DISCOVERY_SYSTEM_PROMPT = """
أنت محرك اكتشاف الأخبار في Saudi Economy Daily، ولست مجرد محلل للقصص التي يرسلها لك النظام.

المهمة: ابحث بنفسك على الويب عن أهم الأخبار الاقتصادية السعودية المنشورة خلال آخر 30 ساعة فقط، ثم أعد قائمة بالقصص الجديدة التي تستحق أن تدخل مرحلة التحقق والتحليل.

قواعد إلزامية:
1. استخدم web_search فعلياً، ولا تعتمد على المعرفة السابقة أو على قائمة RSS فقط.
2. نفّذ عدة عمليات بحث متنوعة تغطي: النفط والطاقة، الأسواق وتاسي، البنوك والتمويل، الشركات والأرباح والاستحواذات، الاستثمار وصندوق الاستثمارات، الحكومة والقرارات الاقتصادية، العقار، السياحة، الصناعة والتعدين، التجارة واللوجستيات، التقنية والوظائف.
3. أعط الأولوية للمصادر السعودية الرسمية والمصادر الاقتصادية الموثوقة ووكالات الأنباء العالمية، ثم المصادر المتخصصة.
4. استخدم web_extract لقراءة صفحات الأخبار المهمة عندما يكون ذلك متاحاً.
5. لا تُرجع قصة إلا إذا أمكن التحقق من أنها نُشرت خلال آخر 30 ساعة. يجب أن يكون published_at بصيغة ISO 8601 مع المنطقة الزمنية إذا كانت معلومة. إذا لم يمكن التحقق من وقت النشر، لا تدرج القصة.
6. لا تكرر نفس الحدث من عدة مواقع. اجمع التغطيات في قصة واحدة واستخدم أفضل رابط أصلي أو أوثق رابط.
7. يجب أن يكون للخبر صلة مباشرة بالاقتصاد السعودي أو تأثير اقتصادي واضح على السعودية.
8. لا تخترع روابط أو أوقات نشر أو أسماء مصادر.
9. ابحث عن قصص لم تكن موجودة في RSS أو قائمة المصادر الأولية؛ هذه هي القيمة الأساسية لهذه المرحلة.
10. رتّب النتائج حسب الأهمية والحداثة، وأعد حتى العدد المطلوب إذا وجدت أخباراً كافية.

أعد JSON فقط:
{
  "discoveries": [
    {
      "title": "عنوان الخبر",
      "url": "https://...",
      "source": "اسم المصدر",
      "published_at": "2026-10-05T10:30:00+03:00",
      "description": "وصف قصير من نتيجة البحث أو الصفحة",
      "category": "oil",
      "importance_hint": 85
    }
  ]
}
""";

def build_discovery_prompt(
    sources: list[dict[str, Any]],
    limit: int,
) -> str:
    source_hints = []

    for source in sources:
        source_hints.append(
            {
                "name": str(source.get("name", ""))[:120],
                "website": str(source.get("url", ""))[:250],
                "type": str(source.get("type", ""))[:80],
                "topics": source.get("topics", [])[:8]
                    if isinstance(source.get("topics", []), list)
                    else [],
            }
        )

    now_utc = datetime.now(timezone.utc).isoformat()

    return f"""
{DISCOVERY_SYSTEM_PROMPT}

الوقت الحالي UTC:
{now_utc}

المصادر الموجودة في المشروع للاسترشاد بها، لكن لا تكتفِ بها:
{json.dumps(source_hints, ensure_ascii=False, indent=2)}

أقصى عدد نتائج:
{limit}

مهم: ابحث عن الأخبار بنفسك. لا تعتبر هذه القائمة مصدراً وحيداً للاكتشاف.
""";

def _parse_discoveries(text: str, limit: int) -> list[dict[str, Any]]:
    payload = _extract_json_from_output(text)

    if not payload:
        return []

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return []

    raw = parsed.get("discoveries", []) if isinstance(parsed, dict) else []
    if not isinstance(raw, list):
        return []

    results = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        source = str(item.get("source", "")).strip()
        published_at = str(item.get("published_at", "")).strip()
        if not title or not url.startswith(("http://", "https://")):
            continue
        if not source or not published_at:
            continue
        try:
            dt = datetime.fromisoformat(
                published_at.replace("Z", "+00:00")
            )
            if dt.tzinfo is None:
                continue
            age = (
                datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
            ).total_seconds() / 3600
            if age < 0 or age > 30:
                continue
        except (TypeError, ValueError):
            continue

        results.append(
            {
                "title": title[:600],
                "url": url[:500],
                "source": source[:150],
                "published_at": published_at[:80],
                "description": str(item.get("description", "")).strip()[:2000],
                "category": str(item.get("category", "economy")).strip()[:50],
                "importance_hint": max(0, min(100, _as_int(item.get("importance_hint"), 0))),
            }
        )
        if len(results) >= limit:
            break

    return results


def discover_articles(
    sources: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    config = load_config()

    if not config["enabled"]:
        return []

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Hermes discovery unavailable: OPENROUTER_API_KEY is missing.")
        return []

    binary = find_hermes_binary()
    if not binary:
        print("Hermes discovery unavailable: hermes executable was not found.")
        return []

    prompt = build_discovery_prompt(
        sources or [],
        config["discovery_limit"],
    )

    runtime_home = tempfile.mkdtemp(prefix="saudi-economy-hermes-discovery-")
    env = os.environ.copy()
    env["OPENROUTER_API_KEY"] = api_key
    env["HERMES_HOME"] = runtime_home
    _write_runtime_config(config, runtime_home)

    command = [
        binary, "chat", "--oneshot", "--query-file", "-",
        "--provider", config.get("provider", "gemini"),
        "--model", config["model"],
        "--toolsets", "web",
        "--max-turns", str(config["discovery_turns"]),
    ]

    print("Starting Hermes news discovery...")
    print(f"Hermes discovery limit: {config['discovery_limit']}")

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
        print("Hermes discovery timed out.")
        shutil.rmtree(runtime_home, ignore_errors=True)
        return []
    except OSError as error:
        print(f"Hermes discovery execution error: {error}")
        shutil.rmtree(runtime_home, ignore_errors=True)
        return []

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    if completed.returncode != 0:
        print(f"Hermes discovery exit code: {completed.returncode}")
        print("===== HERMES DISCOVERY STDERR =====")
        print(stderr[-8000:] if stderr else "(empty)")
        print("===== HERMES DISCOVERY STDOUT =====")
        print(stdout[-8000:] if stdout else "(empty)")
        shutil.rmtree(runtime_home, ignore_errors=True)
        return []

    if stderr:
        print(f"Hermes discovery diagnostics: {stderr[-2000:]}")

    discoveries = _parse_discoveries(stdout, config["discovery_limit"])
    print(f"Hermes discovered {len(discoveries)} recent candidate(s).")

    shutil.rmtree(runtime_home, ignore_errors=True)
    return discoveries


def discoveries_to_articles(
    discoveries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    articles = []
    for item in discoveries:
        title = item["title"]
        url = item["url"]
        articles.append(
            {
                "id": hashlib.sha256(
                    f"{title}|{url}".encode("utf-8")
                ).hexdigest(),
                "title": title,
                "url": url,
                "content": item.get("description") or title,
                "source": item["source"],
                "source_type": "hermes_web",
                "default_content_type": "news",
                "priority": max(1, int(item.get("importance_hint", 0)) // 20),
                "published_at": item["published_at"],
            }
        )
    return articles


def research_articles(
    articles: list[dict[str, Any]],
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:

    config = load_config()

    if not config["enabled"]:
        print(
            "Hermes research disabled by configuration."
        )
        return {}

    api_key = os.getenv(
        "OPENROUTER_API_KEY"
    )

    if not api_key:
        print(
            "Hermes research unavailable: "
            "OPENROUTER_API_KEY is missing."
        )
        return {}

    if not articles:
        return {}

    binary = find_hermes_binary()

    if not binary:
        print(
            "Hermes research unavailable: "
            "hermes executable was not found."
        )
        return {}

    limited_articles = articles[
        :config["max_candidates"]
    ]

    prompt = build_prompt(
        limited_articles,
        sources or [],
    )

    runtime_home = tempfile.mkdtemp(
        prefix="saudi-economy-hermes-"
    )

    env = os.environ.copy()

    env["OPENROUTER_API_KEY"] = api_key
    env["HERMES_HOME"] = runtime_home

    _write_runtime_config(
        config,
        runtime_home,
    )

    command = [
        binary,
        "chat",
        "--oneshot",
        "--query-file",
        "-",
        "--provider",
        config.get("provider", "gemini"),
        "--model",
        config["model"],
        "--toolsets",
        "web",
        "--max-turns",
        str(config["max_turns"]),
    ]

    print(
        "Starting Hermes deep research..."
    )

    print(
        f"Hermes model: {config['model']}"
    )

    print(
        f"Hermes candidates: "
        f"{len(limited_articles)}"
    )

    print(
        f"Hermes binary: {binary}"
    )

    if config.get("web_backend"):
        print(
            "Hermes web backend: "
            f"{config['web_backend']}"
        )
    else:
        print(
            "Hermes web backend: auto-detect"
        )

    try:

        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=config[
                "timeout_seconds"
            ],
            env=env,
            check=False,
        )

    except subprocess.TimeoutExpired:

        print(
            "Hermes research timed out."
        )

        shutil.rmtree(
            runtime_home,
            ignore_errors=True,
        )

        return {}

    except OSError as error:

        print(
            f"Hermes execution error: {error}"
        )

        shutil.rmtree(
            runtime_home,
            ignore_errors=True,
        )

        return {}

    stdout = (
        completed.stdout or ""
    ).strip()

    stderr = (
        completed.stderr or ""
    ).strip()

    if completed.returncode != 0:

        print(
            "Hermes exit code: "
            f"{completed.returncode}"
        )

        print(
            "===== HERMES STDERR ====="
        )

        print(
            stderr[-10000:]
            if stderr
            else "(empty)"
        )

        print(
            "===== HERMES STDOUT ====="
        )

        print(
            stdout[-10000:]
            if stdout
            else "(empty)"
        )

        shutil.rmtree(
            runtime_home,
            ignore_errors=True,
        )

        return {}

    if stderr:

        print(
            "Hermes diagnostics: "
            f"{stderr[-2000:]}"
        )

    # IMPORTANT:
    # Hermes may put reasoning/tool output/progress information
    # in stdout together with the final JSON.
    # Extract only the valid JSON object.
    stdout_for_json = _extract_json_from_output(
        stdout
    )

    if not stdout_for_json:

        print(
            "Hermes returned no JSON content."
        )

        print(
            stdout[:5000]
        )

        shutil.rmtree(
            runtime_home,
            ignore_errors=True,
        )

        return {}

    try:

        results = parse_results(
            stdout_for_json
        )

    except (
        ValueError,
        json.JSONDecodeError,
    ) as error:

        print(
            "Hermes returned invalid JSON: "
            f"{error}"
        )

        print(
            "===== EXTRACTED OUTPUT ====="
        )

        print(
            stdout_for_json[:10000]
        )

        print(
            "===== RAW STDOUT ====="
        )

        print(
            stdout[:5000]
        )

        shutil.rmtree(
            runtime_home,
            ignore_errors=True,
        )

        return {}

    # Only accept results that explicitly report
    # a research pass and include at least one
    # supporting source different from the original source.
    #
    # This prevents a plain rewrite from silently
    # replacing the legacy path.

    validated = {}

    original_by_id = {
        str(a.get("id", "")): str(
            a.get("source", "")
        ).strip()
        for a in limited_articles
    }

    for article_id, result in results.items():

        if not result.get(
            "research_performed"
        ):
            continue

        primary = (
            original_by_id.get(
                article_id,
                "",
            )
            .lower()
        )

        independent_sources = []

        for source in result.get(
            "supporting_sources",
            [],
        ):

            name = str(
                source.get("name", "")
            ).strip()

            if (
                name
                and name.lower() != primary
                and name.lower()
                not in {
                    x.lower()
                    for x in independent_sources
                }
            ):
                independent_sources.append(
                    name
                )

        if not independent_sources:
            continue

        validated[
            article_id
        ] = result

    print(
        "Hermes validated research results: "
        f"{len(validated)}"
    )

    shutil.rmtree(
        runtime_home,
        ignore_errors=True,
    )

    return validated


def supporting_source_names(
    result: dict[str, Any],
    primary_source: str,
) -> list[str]:

    values = []

    primary = (
        primary_source
        .strip()
        .lower()
    )

    sources = (
        result.get(
            "supporting_sources",
            [],
        )
        if isinstance(result, dict)
        else []
    )

    for item in sources:

        if not isinstance(item, dict):
            continue

        name = str(
            item.get("name", "")
        ).strip()

        if (
            not name
            or name.lower() == primary
            or name in values
        ):
            continue

        values.append(name)

        if len(values) >= 5:
            break

    return values
