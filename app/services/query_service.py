import logging
import time
from typing import Optional

from app.models.schemas import QueryRequest, QueryResponse
from app.services.llm_service import LLMService, llm_service
from app.services.query_executor import QueryExecutor, query_executor

logger = logging.getLogger(__name__)


class QueryService:
    """Orchestrates natural language understanding, safe execution, and verified response formulation."""

    def __init__(
        self,
        llm_svc: Optional[LLMService] = None,
        exec_svc: Optional[QueryExecutor] = None
    ):
        self.llm_service = llm_svc or llm_service
        self.query_executor = exec_svc or query_executor

    async def process_question(self, req: QueryRequest) -> QueryResponse:
        """Process natural language question end-to-end with high precision and performance timing."""
        start_time = time.perf_counter()
        question = req.question.strip()

        logger.info(f"Processing query: '{question}'")

        # 1. Parse intent (LLM with deterministic fallback)
        intent = await self.llm_service.parse_query(question)

        # 2. Check for genuine ambiguity
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

        # 3. Execute safe query against database
        exec_result = self.query_executor.execute(intent)

        # 4. Generate final data-backed answer
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
            clarification=None,
            sql_executed=exec_result.get("sql_executed"),
            query_intent=intent.model_dump(mode="json")
        )


# Singleton helper instance
query_service = QueryService()
