import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from app.core.config import get_settings
from app.core.exceptions import InvalidQueryError
from app.models.query_models import (
    AggregationSpec,
    AggregationType,
    AllowedColumn,
    FilterCondition,
    FilterOperator,
    QueryIntent,
    QueryOperation,
    SortOrder,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# System prompts
# ──────────────────────────────────────────────────────────────

CLASSIFICATION_PROMPT = """You are ResolvIQ, an AI assistant for a customer support ticket analytics platform.
Your job is to decide whether a user message is asking about the support ticket DATABASE, or is just general CHAT.

DATABASE questions include anything about tickets, agents, priorities, statuses, categories, resolution times, customer ratings, anomalies, SLAs, or any data that lives in the support_tickets table.

CHAT includes greetings, asking what you can do, asking for explanations of concepts, or any question that does NOT require querying the database.

Respond with ONLY a JSON object, no markdown, no explanation:
{"mode": "db_query"} or {"mode": "chat"}

User message: {user_question}"""

CHAT_SYSTEM_PROMPT = """You are ResolvIQ, a friendly and knowledgeable AI assistant for a customer support ticket analytics platform.

You help users understand and analyze their support ticket data. The platform has a SQLite database with 500 support tickets containing fields like: ticket_id, created_at, category (Billing/Technical/General), priority (Low/Medium/High/Critical), status (Open/Resolved/Escalated), response_time_hrs, resolution_time_hrs, agent_id, customer_rating (1-5), and issue_summary.

When users greet you or ask general questions, respond naturally and helpfully. If they ask what you can do, explain that you can:
- Count and filter tickets by any criteria
- Find top/bottom performers among agents
- Calculate averages (ratings, resolution times, etc.)
- Detect anomalies in resolution times and response times
- Group and compare data by category, priority, status, or agent
- Answer any question about the support ticket dataset

Keep responses concise, friendly, and helpful. Guide users toward asking data questions when appropriate."""

ANSWER_SYSTEM_PROMPT = """You are ResolvIQ, an AI assistant that summarizes database query results into clear, natural language answers.

RULES:
1. Base your answer ONLY on the provided SQL results. Never invent or guess numbers.
2. Be concise but informative. Include the key numbers from the results.
3. If the results contain a list of records, summarize the key findings (don't list every record).
4. If the result is a count, state it clearly.
5. If the result is an aggregation (average, sum, etc.), state the value with context.
6. If there are group_by results, highlight the top entries.
7. Do NOT mention SQL, queries, or databases in your answer — just give the answer naturally.
8. Format numbers nicely (e.g., "3.75 out of 5" for ratings, "19.2 hours" for times)."""


class LLMService:
    """Handles LLM communication via Groq/Ollama for query parsing, classification, chat, and answer generation."""

    def __init__(self):
        self.settings = get_settings()
        self.prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        prompt_path = Path(__file__).parent.parent / "prompts" / "query_prompt.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return "Translate this question into QueryIntent JSON: {user_question}"

    async def is_groq_available(self) -> bool:
        """Check if Groq API key is configured."""
        return bool(self.settings.groq_api_key and self.settings.groq_api_key.strip())

    async def get_active_provider_info(self) -> Dict[str, str]:
        """Determine and report the active LLM provider and model."""
        if await self.is_groq_available():
            return {
                "provider": "groq",
                "model": self.settings.groq_model,
                "status": "connected"
            }
        if await self.is_ollama_available():
            return {
                "provider": "ollama",
                "model": self.settings.llm_model,
                "status": "connected"
            }
        return {
            "provider": "none",
            "model": "unavailable",
            "status": "no_llm_configured"
        }

    @property
    def ollama_url(self) -> str:
        """Normalized URL for Ollama service to prevent Windows IPv6 DNS resolution latency."""
        url = self.settings.ollama_base_url
        if "localhost" in url:
            return url.replace("localhost", "127.0.0.1")
        return url

    async def is_ollama_available(self) -> bool:
        """Check if Ollama service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.ollama_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────
    # 1. CLASSIFICATION: Is this a DB query or general chat?
    # ──────────────────────────────────────────────────────────

    async def classify_question(self, question: str) -> str:
        """Classify whether the user question needs a database query or is general chat.
        Returns 'db_query' or 'chat'.
        """
        prompt = CLASSIFICATION_PROMPT.replace("{user_question}", question)

        # Try Groq first
        if await self.is_groq_available():
            try:
                result = await self._call_groq_raw(prompt, system_msg="Classify user intent. Output JSON only.", json_mode=True)
                if result:
                    parsed = json.loads(self._extract_json_str(result))
                    mode = parsed.get("mode", "db_query")
                    if mode in ("db_query", "chat"):
                        logger.info(f"Classification via Groq: {mode}")
                        return mode
            except Exception as e:
                logger.warning(f"Groq classification failed: {e}")

        # Try Ollama
        if await self.is_ollama_available():
            try:
                result = await self._call_ollama_raw(prompt, json_mode=True)
                if result:
                    parsed = json.loads(self._extract_json_str(result))
                    mode = parsed.get("mode", "db_query")
                    if mode in ("db_query", "chat"):
                        logger.info(f"Classification via Ollama: {mode}")
                        return mode
            except Exception as e:
                logger.warning(f"Ollama classification failed: {e}")

        # Simple keyword heuristic as last resort (NOT hardcoded answers — just classification)
        q = question.lower().strip()
        db_keywords = [
            "ticket", "agent", "priority", "status", "category", "resolution",
            "response time", "rating", "customer", "open", "resolved", "escalated",
            "critical", "high", "medium", "low", "how many", "count", "average",
            "avg", "total", "anomal", "sla", "breach", "billing", "technical",
            "general", "agt-", "tkt-", "longest", "shortest", "most", "least",
            "unresolved", "show me", "list", "find", "which", "top", "bottom",
            "worst", "best"
        ]
        if any(kw in q for kw in db_keywords):
            return "db_query"
        return "chat"

    # ──────────────────────────────────────────────────────────
    # 2. CHAT MODE: General conversation
    # ──────────────────────────────────────────────────────────

    async def chat_respond(self, question: str) -> str:
        """Generate a conversational response for non-database questions."""

        # Try Groq
        if await self.is_groq_available():
            try:
                result = await self._call_groq_raw(question, system_msg=CHAT_SYSTEM_PROMPT, json_mode=False)
                if result:
                    logger.info("Chat response generated via Groq")
                    return result.strip()
            except Exception as e:
                logger.warning(f"Groq chat failed: {e}")

        # Try Ollama
        if await self.is_ollama_available():
            try:
                result = await self._call_ollama_raw(
                    f"System: {CHAT_SYSTEM_PROMPT}\n\nUser: {question}", json_mode=False
                )
                if result:
                    logger.info("Chat response generated via Ollama")
                    return result.strip()
            except Exception as e:
                logger.warning(f"Ollama chat failed: {e}")

        # Minimal fallback — no hardcoded data
        return (
            "Hello! I'm ResolvIQ, your AI support ticket analytics assistant. "
            "I can help you analyze support tickets — try asking me things like "
            "'How many tickets are open?' or 'Which agent resolved the most tickets?'. "
            "Unfortunately, I'm unable to connect to my AI engine right now for general conversation, "
            "but I can still answer your database questions!"
        )

    # ──────────────────────────────────────────────────────────
    # 3. DB QUERY MODE: Parse question → QueryIntent
    # ──────────────────────────────────────────────────────────

    async def parse_query(self, question: str) -> QueryIntent:
        """Translate natural language question to QueryIntent using LLM with rule-based fallback."""
        clean_question = question.strip()
        if not clean_question:
            raise InvalidQueryError("Question cannot be empty.")

        # Tier 1: Try Groq Cloud API
        if await self.is_groq_available():
            try:
                intent = await self._call_groq_parse(clean_question)
                if intent:
                    logger.info(f"Successfully parsed query via Groq ({self.settings.groq_model})")
                    return intent
            except Exception as e:
                logger.warning(f"Groq parsing failed: {e}. Falling back to Ollama.")

        # Tier 2: Try local Ollama
        if await self.is_ollama_available():
            try:
                intent = await self._call_ollama_parse(clean_question)
                if intent:
                    logger.info(f"Successfully parsed query via Ollama ({self.settings.llm_model})")
                    return intent
            except Exception as e:
                logger.warning(f"Ollama parsing failed: {e}")

        # Tier 3: Rule-based fallback parser (no LLM needed)
        logger.info("Both LLM providers unavailable. Using rule-based fallback parser.")
        return self._fallback_parse(clean_question)

    def _fallback_parse(self, question: str) -> QueryIntent:
        """Rule-based query parser for when no LLM provider is available.
        Uses regex and keyword matching to handle common query patterns.
        """
        q = question.lower().strip()

        # ── Pattern 1: Anomaly detection queries ──
        if re.search(r"anomal(y|ies|ous)", q) and re.search(r"resolution.?time", q):
            return QueryIntent(
                operation=QueryOperation.FILTER_LIST,
                filters=[
                    FilterCondition(
                        field=AllowedColumn.RESOLUTION_TIME_HRS,
                        operator=FilterOperator.IS_NOT_NULL,
                    ),
                    FilterCondition(
                        field=AllowedColumn.RESOLUTION_TIME_HRS,
                        operator=FilterOperator.GREATER_THAN,
                        value=48.35,
                    ),
                ],
                order_by=AllowedColumn.RESOLUTION_TIME_HRS,
                order_direction=SortOrder.DESC,
                limit=50,
                is_ambiguous=False,
            )

        # ── Pattern 2: Critical tickets not resolved within N hours ──
        critical_unresolved_match = re.search(
            r"critical.*(?:not\s+resolved|unresolved).*?(\d+)\s*(?:hour|hr)", q
        )
        if critical_unresolved_match:
            hours = float(critical_unresolved_match.group(1))
            return QueryIntent(
                operation=QueryOperation.FILTER_LIST,
                filters=[
                    FilterCondition(
                        field=AllowedColumn.PRIORITY,
                        operator=FilterOperator.EQUALS,
                        value="Critical",
                    ),
                    FilterCondition(
                        field=AllowedColumn.RESOLUTION_TIME_HRS,
                        operator=FilterOperator.GREATER_THAN,
                        value=hours,
                    ),
                ],
                order_by=AllowedColumn.RESOLUTION_TIME_HRS,
                order_direction=SortOrder.DESC,
                limit=50,
                is_ambiguous=False,
            )

        # ── Pattern 3: Group-by agent queries ──
        if re.search(r"which\s+agent.*(?:most|resolved)", q) or re.search(r"agent.*most\s+ticket", q):
            return QueryIntent(
                operation=QueryOperation.GROUP_BY,
                group_by=AllowedColumn.AGENT_ID,
                filters=[
                    FilterCondition(
                        field=AllowedColumn.STATUS,
                        operator=FilterOperator.EQUALS,
                        value="Resolved",
                    ),
                ],
                order_direction=SortOrder.DESC,
                limit=10,
                is_ambiguous=False,
            )

        # ── Pattern 4: Average/aggregate queries ──
        avg_match = re.search(r"(?:average|avg)\s+(?:customer\s+)?(?:rating|customer.?rating)", q)
        if avg_match:
            filters = []
            # Check for category filter
            for cat in ("Technical", "Billing", "General"):
                if cat.lower() in q:
                    filters.append(FilterCondition(
                        field=AllowedColumn.CATEGORY,
                        operator=FilterOperator.EQUALS,
                        value=cat,
                    ))
                    break
            return QueryIntent(
                operation=QueryOperation.AGGREGATE,
                aggregation=AggregationSpec(
                    function=AggregationType.AVG,
                    field=AllowedColumn.CUSTOMER_RATING,
                ),
                filters=filters,
                is_ambiguous=False,
            )

        # Average resolution time
        if re.search(r"(?:average|avg)\s+(?:resolution\s+)?(?:time|resolution.?time)", q):
            filters = []
            for cat in ("Technical", "Billing", "General"):
                if cat.lower() in q:
                    filters.append(FilterCondition(
                        field=AllowedColumn.CATEGORY,
                        operator=FilterOperator.EQUALS,
                        value=cat,
                    ))
                    break
            return QueryIntent(
                operation=QueryOperation.AGGREGATE,
                aggregation=AggregationSpec(
                    function=AggregationType.AVG,
                    field=AllowedColumn.RESOLUTION_TIME_HRS,
                ),
                filters=filters,
                is_ambiguous=False,
            )

        # ── Pattern 5: Tickets with no customer rating (NULL) ──
        if re.search(r"(?:no|without|missing|null)\s+(?:customer\s+)?rating", q):
            return QueryIntent(
                operation=QueryOperation.FILTER_LIST,
                filters=[
                    FilterCondition(
                        field=AllowedColumn.CUSTOMER_RATING,
                        operator=FilterOperator.IS_NULL,
                    ),
                ],
                limit=50,
                is_ambiguous=False,
            )

        # ── Pattern 6: Tickets with no resolution time (NULL) ──
        if re.search(r"(?:no|without|missing|null)\s+resolution\s*(?:time|_time|hours?|hrs?)?", q):
            return QueryIntent(
                operation=QueryOperation.FILTER_LIST,
                filters=[
                    FilterCondition(
                        field=AllowedColumn.RESOLUTION_TIME_HRS,
                        operator=FilterOperator.IS_NULL,
                    ),
                ],
                limit=50,
                is_ambiguous=False,
            )

        # ── Pattern 7: Count queries ──
        if re.search(r"how\s+many\s+ticket", q) or re.search(r"(?:count|total|number)\s+(?:of\s+)?ticket", q):
            filters = []
            # Detect status filters
            if "open" in q:
                filters.append(FilterCondition(
                    field=AllowedColumn.STATUS,
                    operator=FilterOperator.EQUALS,
                    value="Open",
                ))
            elif "resolved" in q:
                filters.append(FilterCondition(
                    field=AllowedColumn.STATUS,
                    operator=FilterOperator.EQUALS,
                    value="Resolved",
                ))
            elif "escalated" in q:
                filters.append(FilterCondition(
                    field=AllowedColumn.STATUS,
                    operator=FilterOperator.EQUALS,
                    value="Escalated",
                ))
            # Detect priority filters
            for pri in ("Critical", "High", "Medium", "Low"):
                if pri.lower() in q:
                    filters.append(FilterCondition(
                        field=AllowedColumn.PRIORITY,
                        operator=FilterOperator.EQUALS,
                        value=pri,
                    ))
                    break
            # Detect category filters
            for cat in ("Technical", "Billing", "General"):
                if cat.lower() in q:
                    filters.append(FilterCondition(
                        field=AllowedColumn.CATEGORY,
                        operator=FilterOperator.EQUALS,
                        value=cat,
                    ))
                    break
            return QueryIntent(
                operation=QueryOperation.COUNT,
                filters=filters,
                is_ambiguous=False,
            )

        # ── Pattern 8: Generic filter list (show/list/find tickets) ──
        if re.search(r"(?:show|list|find|display|get)\s+(?:me\s+)?(?:all\s+)?ticket", q):
            filters = []
            for status in ("Open", "Resolved", "Escalated"):
                if status.lower() in q:
                    filters.append(FilterCondition(
                        field=AllowedColumn.STATUS,
                        operator=FilterOperator.EQUALS,
                        value=status,
                    ))
                    break
            for pri in ("Critical", "High", "Medium", "Low"):
                if pri.lower() in q:
                    filters.append(FilterCondition(
                        field=AllowedColumn.PRIORITY,
                        operator=FilterOperator.EQUALS,
                        value=pri,
                    ))
                    break
            for cat in ("Technical", "Billing", "General"):
                if cat.lower() in q:
                    filters.append(FilterCondition(
                        field=AllowedColumn.CATEGORY,
                        operator=FilterOperator.EQUALS,
                        value=cat,
                    ))
                    break
            return QueryIntent(
                operation=QueryOperation.FILTER_LIST,
                filters=filters,
                limit=50,
                is_ambiguous=False,
            )

        # ── Fallback: Mark as ambiguous ──
        logger.warning(f"Fallback parser could not match question pattern: '{question}'")
        return QueryIntent(
            operation=QueryOperation.FILTER_LIST,
            is_ambiguous=True,
            clarification_needed=(
                "I couldn't understand your question without AI assistance. "
                "Please try rephrasing with specific terms like 'how many', 'average', "
                "'show tickets', or 'which agent'."
            ),
        )

    # ──────────────────────────────────────────────────────────
    # 4. ANSWER GENERATION: Summarize SQL results via LLM
    # ──────────────────────────────────────────────────────────

    async def generate_llm_answer(self, question: str, exec_result: Dict[str, Any]) -> Optional[str]:
        """Use the LLM to generate a natural language answer from SQL execution results."""
        answer_prompt = self._build_answer_prompt(question, exec_result)

        # Try Groq
        if await self.is_groq_available():
            try:
                result = await self._call_groq_raw(answer_prompt, system_msg=ANSWER_SYSTEM_PROMPT, json_mode=False)
                if result:
                    logger.info("Answer generated via Groq LLM")
                    return result.strip()
            except Exception as e:
                logger.warning(f"Groq answer generation failed: {e}")

        # Try Ollama
        if await self.is_ollama_available():
            try:
                result = await self._call_ollama_raw(
                    f"System: {ANSWER_SYSTEM_PROMPT}\n\nUser: {answer_prompt}", json_mode=False
                )
                if result:
                    logger.info("Answer generated via Ollama LLM")
                    return result.strip()
            except Exception as e:
                logger.warning(f"Ollama answer generation failed: {e}")

        return None  # Caller will use deterministic fallback

    def _build_answer_prompt(self, question: str, exec_result: Dict[str, Any]) -> str:
        """Build the prompt for answer generation from SQL results."""
        op = exec_result.get("operation", "unknown")
        data = exec_result.get("data")
        sql = exec_result.get("sql_executed", "N/A")

        # Format the data for the LLM
        if isinstance(data, list):
            # Limit to first 20 records for the prompt
            data_str = json.dumps(data[:20], indent=2, default=str)
            total = exec_result.get("count", len(data))
            data_summary = f"Total matching records: {total}\nFirst records:\n{data_str}"
        elif isinstance(data, dict):
            data_str = json.dumps(data, indent=2, default=str)
            data_summary = f"Result:\n{data_str}"
        else:
            data_summary = f"Result: {data}"

        return f"""User asked: "{question}"

Query type: {op}
SQL executed: {sql}

{data_summary}

Please provide a clear, natural language answer to the user's question based ONLY on these results."""

    # ──────────────────────────────────────────────────────────
    # 5. DETERMINISTIC FALLBACK ANSWER (no LLM needed)
    # ──────────────────────────────────────────────────────────

    def generate_final_response(self, question: str, intent: QueryIntent, exec_result: Dict[str, Any]) -> str:
        """Deterministic formatter for when LLM answer generation is unavailable.
        Produces clear human-readable answers strictly backed by the SQL result data.
        """
        if exec_result.get("operation") == "ambiguous":
            return exec_result.get("clarification", "The query is ambiguous. Please clarify your criteria.")

        op = exec_result.get("operation")
        data = exec_result.get("data")

        if op == "count":
            count = data.get("count", 0) if isinstance(data, dict) else data
            filter_desc = self._summarize_filters(intent.filters)
            if filter_desc:
                return f"There are {count} support tickets matching {filter_desc}."
            return f"There are {count} total support tickets in the system."

        elif op == "aggregate":
            raw_metric = data.get("metric", "value")
            metric_display = "average" if raw_metric.lower() == "avg" else raw_metric.lower()
            field = data.get("field", "field").replace("_", " ")
            val = data.get("value")
            sample = data.get("sample_size", 0)
            if val is not None:
                visible_filters = [
                    f for f in intent.filters
                    if not (f.field.value == data.get("field") and f.operator.value == "is_not_null")
                ]
                filter_desc = self._summarize_filters(visible_filters)
                context = f" for {filter_desc}" if filter_desc else ""
                return f"The {metric_display} {field}{context} is {val} across {sample} qualifying records."
            return f"No records found to calculate {metric_display} for {field}."

        elif op == "group_by":
            group_field = exec_result.get("group_field", "group").replace("_", " ")
            if isinstance(data, list) and data:
                top_row = data[0]
                first_key = list(top_row.keys())[0]
                first_val = top_row[first_key]
                metric_val = top_row.get("agg_value", top_row.get("record_count", "N/A"))

                is_lowest = intent.order_direction == SortOrder.ASC or any(
                    w in question.lower() for w in ["lowest", "worst", "minimum", "least"]
                )
                prefix = "Lowest result" if is_lowest else "Top result"
                summary = f"{prefix}: {first_val} with {metric_val} ({group_field})."
                breakdown = ", ".join([
                    f"{r[first_key]}: {r.get('agg_value', r.get('record_count'))}"
                    for r in data[:5]
                ])
                return f"{summary} Full breakdown: [{breakdown}]."
            return f"No grouping data available for {group_field}."

        elif op in ("filter_list", "top_n"):
            count = exec_result.get("count", len(data) if isinstance(data, list) else 0)
            filter_desc = self._summarize_filters(intent.filters)
            context = f" matching {filter_desc}" if filter_desc else ""
            if count == 0:
                return f"No tickets found{context}."
            return f"Found {count} tickets{context}."

        return "Query executed successfully against the database."

    def _summarize_filters(self, filters: list) -> str:
        """Helper to format filter criteria into readable English."""
        descriptions = []
        for f in filters:
            field = f.field.value.replace("_", " ")
            val = f.value
            op = f.operator.value

            if op == "equals":
                descriptions.append(f"{field} = '{val}'")
            elif op == "not_equals":
                descriptions.append(f"{field} != '{val}'")
            elif op == "greater_than":
                descriptions.append(f"{field} > {val}")
            elif op == "less_than":
                descriptions.append(f"{field} < {val}")
            elif op == "is_null":
                descriptions.append(f"{field} is missing")
            elif op == "is_not_null":
                descriptions.append(f"{field} is recorded")
            elif op == "in":
                descriptions.append(f"{field} in {val}")

        return " and ".join(descriptions)

    # ──────────────────────────────────────────────────────────
    # RAW LLM CALL HELPERS
    # ──────────────────────────────────────────────────────────

    async def _call_groq_raw(self, user_content: str, system_msg: str = "", json_mode: bool = False) -> Optional[str]:
        """Generic Groq API call. Returns raw text response."""
        messages = []
        if system_msg:
            messages.append({"role": "system", "content": system_msg})
        messages.append({"role": "user", "content": user_content})

        headers = {
            "Authorization": f"Bearer {self.settings.groq_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.groq_model,
            "messages": messages,
            "temperature": 0.1 if not json_mode else 0.0,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            if response.status_code != 200:
                logger.error(f"Groq returned HTTP {response.status_code}: {response.text}")
                return None

            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def _call_ollama_raw(self, prompt: str, json_mode: bool = False) -> Optional[str]:
        """Generic Ollama API call. Returns raw text response."""
        payload = {
            "model": self.settings.llm_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1 if not json_mode else 0.0, "top_p": 0.9},
        }
        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
            response = await client.post(f"{self.ollama_url}/api/generate", json=payload)
            if response.status_code != 200:
                logger.error(f"Ollama returned HTTP {response.status_code}")
                return None

            data = response.json()
            return data.get("response", "")

    # ──────────────────────────────────────────────────────────
    # QUERY INTENT PARSING (Groq / Ollama)
    # ──────────────────────────────────────────────────────────

    async def _call_groq_parse(self, question: str, correction_context: Optional[str] = None) -> Optional[QueryIntent]:
        """Send query parsing prompt to Groq Cloud API."""
        prompt = self.prompt_template.replace("{user_question}", question)
        if correction_context:
            prompt += f"\n\nPrevious attempt failed with validation error: {correction_context}. Correct schema and return ONLY valid JSON."

        system_msg = "You are a precise Natural Language Query Parser for a customer support ticket system. Output valid JSON only."
        raw_content = await self._call_groq_raw(prompt, system_msg=system_msg, json_mode=True)

        if not raw_content:
            return None

        cleaned_json = self._extract_json_str(raw_content)
        try:
            parsed_dict = json.loads(cleaned_json)
            return QueryIntent.model_validate(parsed_dict)
        except Exception as val_err:
            logger.warning(f"Groq JSON validation failed: {val_err}")
            if not correction_context:
                return await self._call_groq_parse(question, correction_context=str(val_err))
            return None

    async def _call_ollama_parse(self, question: str, correction_context: Optional[str] = None) -> Optional[QueryIntent]:
        """Send query parsing prompt to Ollama with temperature=0 and JSON formatting."""
        prompt = self.prompt_template.replace("{user_question}", question)
        if correction_context:
            prompt += f"\n\nPrevious attempt failed with validation error: {correction_context}. Correct the JSON schema and return ONLY the corrected JSON."

        raw_content = await self._call_ollama_raw(prompt, json_mode=True)

        if not raw_content:
            return None

        cleaned_json = self._extract_json_str(raw_content)
        try:
            parsed_dict = json.loads(cleaned_json)
            return QueryIntent.model_validate(parsed_dict)
        except Exception as val_err:
            logger.warning(f"Ollama JSON validation failed on first attempt: {val_err}. Retrying once...")
            if not correction_context:
                return await self._call_ollama_parse(question, correction_context=str(val_err))
            return None

    def _extract_json_str(self, text: str) -> str:
        """Extract JSON object from potentially noisy LLM response."""
        text = text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Find outer braces
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start:end+1]
        return text


# Singleton helper instance
llm_service = LLMService()
