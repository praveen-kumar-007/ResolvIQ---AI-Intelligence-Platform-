import logging
import time
from typing import Optional

from app.models.schemas import QueryRequest, QueryResponse
from app.services.llm_service import LLMService, llm_service
from app.services.query_executor import QueryExecutor, query_executor

logger = logging.getLogger(__name__)


class QueryService:
    """Orchestrates two-mode query processing: general chat and SQL-backed database queries."""

    def __init__(
        self,
        llm_svc: Optional[LLMService] = None,
        exec_svc: Optional[QueryExecutor] = None
    ):
        self.llm_service = llm_svc or llm_service
        self.query_executor = exec_svc or query_executor

    async def process_question(self, req: QueryRequest) -> QueryResponse:
        """Process natural language question with two-mode detection: chat or database query."""
        start_time = time.perf_counter()
        question = req.question.strip()

        logger.info(f"Processing query: '{question}'")

        # ── Step 1: Classify the question ──
        mode = await self.llm_service.classify_question(question)
        logger.info(f"Question classified as: {mode}")

        # ── Step 2: Handle CHAT mode ──
        if mode == "chat":
            chat_response = await self.llm_service.chat_respond(question)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            return QueryResponse(
                question=question,
                answer=chat_response,
                query_type="chat",
                filters=[],
                result=None,
                execution_time_ms=duration_ms,
                is_ambiguous=False,
                is_chat_response=True,
                clarification=None,
            )

        # ── Step 3: DB QUERY mode — Parse intent via LLM ──
        try:
            intent = await self.llm_service.parse_query(question)
        except Exception as e:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(f"Query parsing failed: {e}")
            return QueryResponse(
                question=question,
                answer=str(e),
                query_type="error",
                filters=[],
                result=None,
                execution_time_ms=duration_ms,
                is_ambiguous=True,
                clarification=str(e),
            )

        # ── Step 4: Check for ambiguity ──
        if intent.is_ambiguous:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return QueryResponse(
                question=question,
                answer=intent.clarification_needed or "The question is ambiguous. Please provide more specifics.",
                query_type="ambiguous",
                filters=[],
                result=None,
                execution_time_ms=duration_ms,
                is_ambiguous=True,
                clarification=intent.clarification_needed
            )

        # ── Step 5: Execute safe SQL query against database ──
        exec_result = self.query_executor.execute(intent)

        # ── Step 6: Generate answer (LLM first, deterministic fallback) ──
        answer = None
        try:
            answer = await self.llm_service.generate_llm_answer(question, exec_result)
        except Exception as e:
            logger.warning(f"LLM answer generation failed: {e}")

        if not answer:
            # Fall back to deterministic formatter
            answer = self.llm_service.generate_final_response(question, intent, exec_result)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Format filters for response
        serialized_filters = [
            {"field": f.field.value, "operator": f.operator.value, "value": f.value}
            for f in intent.filters
        ]

        logger.info(f"Query completed in {duration_ms}ms with operation={intent.operation.value}")

        return QueryResponse(
            question=question,
            answer=answer,
            query_type=intent.operation.value,
            filters=serialized_filters,
            result=exec_result.get("data"),
            execution_time_ms=duration_ms,
            is_ambiguous=False,
            is_chat_response=False,
            clarification=None,
            sql_executed=exec_result.get("sql_executed"),
            query_intent=intent.model_dump(mode="json")
        )


# Singleton helper instance
query_service = QueryService()
