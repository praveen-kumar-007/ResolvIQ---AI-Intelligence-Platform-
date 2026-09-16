import logging
from typing import Any, Dict, List, Tuple
from app.core.exceptions import QueryExecutionError
from app.models.query_models import (
    AllowedColumn,
    FilterCondition,
    FilterOperator,
    QueryIntent,
    QueryOperation,
    SortOrder,
)
from app.services.data_service import DataService, data_service

logger = logging.getLogger(__name__)

# Operator to SQL mapping
OPERATOR_SQL_MAP = {
    FilterOperator.EQUALS: "=",
    FilterOperator.NOT_EQUALS: "!=",
    FilterOperator.GREATER_THAN: ">",
    FilterOperator.LESS_THAN: "<",
    FilterOperator.GREATER_THAN_OR_EQUAL: ">=",
    FilterOperator.LESS_THAN_OR_EQUAL: "<=",
}


class QueryExecutor:
    """Safely builds and executes parameterized SQLite queries from validated QueryIntent objects."""

    def __init__(self, data_svc: DataService = data_service):
        self.data_service = data_svc

    def execute(self, intent: QueryIntent) -> Dict[str, Any]:
        """Execute the validated intent against SQLite using strictly parameterized queries."""
        if intent.is_ambiguous:
            return {
                "operation": "ambiguous",
                "data": None,
                "clarification": intent.clarification_needed or "The question is ambiguous. Please specify fields or criteria.",
            }

        operation = intent.operation

        if operation == QueryOperation.COUNT:
            return self._execute_count(intent)
        elif operation == QueryOperation.AGGREGATE:
            return self._execute_aggregate(intent)
        elif operation == QueryOperation.GROUP_BY:
            return self._execute_group_by(intent)
        elif operation in (QueryOperation.FILTER_LIST, QueryOperation.TOP_N):
            return self._execute_filter_list(intent)
        else:
            raise QueryExecutionError(f"Unsupported query operation: '{operation}'")

    def _build_where_clause(self, filters: List[FilterCondition]) -> Tuple[str, List[Any]]:
        """Construct parameterized SQL WHERE clause ensuring field whitelisting."""
        clauses: List[str] = []
        params: List[Any] = []

        for f in filters:
            # Field is guaranteed to be an AllowedColumn enum from Pydantic validation
            field_name = f.field.value

            if f.operator in OPERATOR_SQL_MAP:
                sql_op = OPERATOR_SQL_MAP[f.operator]
                clauses.append(f"{field_name} {sql_op} ?")
                params.append(f.value)
            elif f.operator == FilterOperator.IS_NULL:
                clauses.append(f"{field_name} IS NULL")
            elif f.operator == FilterOperator.IS_NOT_NULL:
                clauses.append(f"{field_name} IS NOT NULL")
            elif f.operator == FilterOperator.IN:
                if isinstance(f.value, (list, tuple)) and f.value:
                    placeholders = ", ".join(["?"] * len(f.value))
                    clauses.append(f"{field_name} IN ({placeholders})")
                    params.extend(list(f.value))
                else:
                    clauses.append(f"{field_name} = ?")
                    params.append(f.value)
            elif f.operator == FilterOperator.LIKE:
                clauses.append(f"{field_name} LIKE ?")
                params.append(f"%{f.value}%")

        where_stmt = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return where_stmt, params

    def _execute_count(self, intent: QueryIntent) -> Dict[str, Any]:
        """Execute a COUNT query."""
        where_stmt, params = self._build_where_clause(intent.filters)
        sql = f"SELECT COUNT(*) AS total_count FROM support_tickets {where_stmt};"

        with self.data_service.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            count = cursor.fetchone()["total_count"]

        return {
            "operation": "count",
            "data": {"count": count},
            "sql_executed": sql,
            "params": params,
        }

    def _execute_aggregate(self, intent: QueryIntent) -> Dict[str, Any]:
        """Execute an aggregation (AVG, SUM, MIN, MAX) query."""
        if not intent.aggregation:
            raise QueryExecutionError("Aggregation operation requires an aggregation specification.")

        agg_func = intent.aggregation.function.value.upper()
        agg_field = intent.aggregation.field.value

        # Make sure target field is numeric
        if agg_field not in ("response_time_hrs", "resolution_time_hrs", "customer_rating"):
            raise QueryExecutionError(f"Cannot perform mathematical aggregation '{agg_func}' on non-numeric column '{agg_field}'")

        # Automatically exclude NULL values for calculations
        filters = list(intent.filters)
        filters.append(
            FilterCondition(
                field=AllowedColumn(agg_field),
                operator=FilterOperator.IS_NOT_NULL
            )
        )

        where_stmt, params = self._build_where_clause(filters)
        sql = f"SELECT {agg_func}({agg_field}) AS metric_val, COUNT({agg_field}) AS sample_size FROM support_tickets {where_stmt};"

        with self.data_service.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            raw_val = row["metric_val"]
            sample_size = row["sample_size"]

        result_val = round(float(raw_val), 2) if raw_val is not None else None

        return {
            "operation": "aggregate",
            "data": {
                "metric": agg_func.lower(),
                "field": agg_field,
                "value": result_val,
                "sample_size": sample_size,
            },
            "sql_executed": sql,
            "params": params,
        }

    def _execute_group_by(self, intent: QueryIntent) -> Dict[str, Any]:
        """Execute a GROUP BY aggregation query."""
        if not intent.group_by:
            raise QueryExecutionError("GROUP_BY operation requires a group_by column specification.")

        group_col = intent.group_by.value
        agg_spec = intent.aggregation

        if agg_spec:
            agg_func = agg_spec.function.value.upper()
            agg_field = agg_spec.field.value
            agg_expr = f"{agg_func}({agg_field}) AS agg_value"
            count_expr = f"COUNT(*) AS record_count"
            select_expr = f"{group_col}, {agg_expr}, {count_expr}"
        else:
            agg_expr = "COUNT(*) AS agg_value"
            select_expr = f"{group_col}, {agg_expr}"

        where_stmt, params = self._build_where_clause(intent.filters)

        order_dir = "DESC" if intent.order_direction == SortOrder.DESC else "ASC"
        order_by_clause = f"ORDER BY agg_value {order_dir}"

        limit_clause = f"LIMIT {intent.limit}" if intent.limit else "LIMIT 50"

        sql = f"""
            SELECT {select_expr}
            FROM support_tickets
            {where_stmt}
            GROUP BY {group_col}
            {order_by_clause}
            {limit_clause};
        """

        results: List[Dict[str, Any]] = []
        with self.data_service.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            for row in cursor.fetchall():
                row_dict = dict(row)
                if "agg_value" in row_dict and row_dict["agg_value"] is not None:
                    row_dict["agg_value"] = round(float(row_dict["agg_value"]), 2) if isinstance(row_dict["agg_value"], float) else row_dict["agg_value"]
                results.append(row_dict)

        return {
            "operation": "group_by",
            "group_field": group_col,
            "data": results,
            "sql_executed": sql.strip(),
            "params": params,
        }

    def _execute_filter_list(self, intent: QueryIntent) -> Dict[str, Any]:
        """Execute a filter query returning ticket rows or top N items."""
        where_stmt, params = self._build_where_clause(intent.filters)

        # Build ORDER BY
        order_clause = ""
        if intent.order_by:
            order_col = intent.order_by.value
            order_dir = "DESC" if intent.order_direction == SortOrder.DESC else "ASC"
            order_clause = f"ORDER BY {order_col} {order_dir}"
        else:
            order_clause = "ORDER BY created_at DESC"

        limit_val = intent.limit or (10 if intent.operation == QueryOperation.TOP_N else 50)
        limit_clause = f"LIMIT {limit_val}"

        sql = f"SELECT * FROM support_tickets {where_stmt} {order_clause} {limit_clause};"

        results: List[Dict[str, Any]] = []
        with self.data_service.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            results = [dict(row) for row in cursor.fetchall()]

        return {
            "operation": intent.operation.value,
            "data": results,
            "count": len(results),
            "sql_executed": sql,
            "params": params,
        }


# Singleton helper instance
query_executor = QueryExecutor()
