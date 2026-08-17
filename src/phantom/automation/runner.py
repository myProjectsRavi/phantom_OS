"""Recipe step-by-step execution engine."""

from __future__ import annotations

import ast
import asyncio
import logging
import time

from phantom.actions.executor import ActionExecutor
from phantom.events import EventBus, PhantomEvents
from phantom.models import ActionRequest, PhantomActionType, Recipe

logger = logging.getLogger("phantom.runner")


class RecipeRunner:
    def __init__(self, executor: ActionExecutor, event_bus: EventBus | None = None):
        self._executor = executor
        self._events = event_bus or EventBus()

    async def run(self, recipe: Recipe, variables: dict | None = None) -> dict:
        """Execute a recipe step by step with fail-closed conditions."""
        values = {**recipe.variables, **(variables or {})}
        values["clipboard"] = self._executor.clipboard.get()
        values["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

        self._events.emit(
            PhantomEvents.RECIPE_TRIGGERED,
            {"recipe": recipe.name, "steps": len(recipe.steps)},
        )

        results: list[dict[str, object]] = []
        start = time.time()

        for index, step in enumerate(recipe.steps):
            if step.condition:
                try:
                    condition_matches = self._condition_true(step.condition, values)
                except Exception as exc:  # noqa: BLE001
                    error = f"Invalid recipe condition at step {index}: {exc}"
                    logger.warning(error)
                    self._events.emit(
                        PhantomEvents.RECIPE_FAILED,
                        {"recipe": recipe.name, "step": index, "error": error},
                    )
                    return {
                        "success": False,
                        "error": error,
                        "step": index,
                        "results": results,
                        "duration_ms": (time.time() - start) * 1000,
                    }
                if not condition_matches:
                    results.append({"step": index, "skipped": True})
                    continue

            params = self._interpolate(step.params, values)
            try:
                action_type = PhantomActionType(step.type)
            except ValueError:
                error = f"Unknown recipe action type: {step.type}"
                self._events.emit(
                    PhantomEvents.RECIPE_FAILED,
                    {"recipe": recipe.name, "step": index, "error": error},
                )
                return {
                    "success": False,
                    "error": error,
                    "step": index,
                    "results": results,
                    "duration_ms": (time.time() - start) * 1000,
                }

            request = ActionRequest(
                type=action_type,
                params=params,
                source=f"recipe:{recipe.name}",
            )

            max_attempts = max(1, int(step.max_retries))
            for attempt in range(max_attempts):
                result = await self._executor.execute(request)
                if result.success:
                    results.append({"step": index, "success": True, "ms": result.duration_ms})
                    if action_type == PhantomActionType.CLIPBOARD_COPY:
                        values["clipboard"] = result.metadata.get("content", "")
                    elif action_type == PhantomActionType.CLIPBOARD_SET:
                        values["clipboard"] = str(params.get("content", ""))
                    break

                if step.on_error == "abort":
                    self._events.emit(
                        PhantomEvents.RECIPE_FAILED,
                        {"recipe": recipe.name, "step": index, "error": result.error},
                    )
                    return {
                        "success": False,
                        "error": result.error,
                        "step": index,
                        "results": results,
                        "duration_ms": (time.time() - start) * 1000,
                    }

                if attempt == max_attempts - 1:
                    results.append({"step": index, "success": False, "error": result.error})

            if step.delay_after > 0:
                await asyncio.sleep(step.delay_after)

        recipe.run_count += 1
        recipe.last_run = time.time()
        duration = (time.time() - start) * 1000
        success = all(item.get("success", True) for item in results)
        recipe.success_rate = (
            recipe.success_rate * (recipe.run_count - 1) + (1 if success else 0)
        ) / recipe.run_count

        self._events.emit(
            PhantomEvents.RECIPE_COMPLETED,
            {"recipe": recipe.name, "success": success, "ms": duration},
        )
        return {"success": success, "results": results, "duration_ms": duration}

    def _interpolate(self, params: dict, values: dict) -> dict:
        result = {}
        for key, value in params.items():
            if isinstance(value, str):
                for variable, replacement in values.items():
                    value = value.replace(f"{{{variable}}}", str(replacement))
            result[key] = value
        return result

    def _condition_true(self, expression: str, values: dict) -> bool:
        tree = ast.parse(expression, mode="eval")
        return bool(self._eval_node(tree.body, values))

    def _eval_node(self, node: ast.AST, values: dict):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return values.get(node.id)
        if isinstance(node, ast.BoolOp):
            items = [self._eval_node(value, values) for value in node.values]
            if isinstance(node.op, ast.And):
                return all(items)
            if isinstance(node.op, ast.Or):
                return any(items)
            raise ValueError("Unsupported boolean operator")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not self._eval_node(node.operand, values)
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, values)
            for operator, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator, values)
                if isinstance(operator, ast.Eq):
                    ok = left == right
                elif isinstance(operator, ast.NotEq):
                    ok = left != right
                elif isinstance(operator, ast.Lt):
                    ok = left < right
                elif isinstance(operator, ast.LtE):
                    ok = left <= right
                elif isinstance(operator, ast.Gt):
                    ok = left > right
                elif isinstance(operator, ast.GtE):
                    ok = left >= right
                elif isinstance(operator, ast.In):
                    ok = left in right
                elif isinstance(operator, ast.NotIn):
                    ok = left not in right
                else:
                    raise ValueError("Unsupported comparator")
                if not ok:
                    return False
                left = right
            return True
        raise ValueError(f"Unsupported condition expression: {type(node).__name__}")
