from __future__ import annotations

import ast
from typing import Any


class UnsafeExpressionError(ValueError):
    """Raised when a rule expression contains unsupported constructs."""


class RuleEvaluator:
    """Safely evaluates rule expressions using Python's AST module."""

    _allowed_nodes = {
        ast.Expression,
        ast.BoolOp,
        ast.BinOp,
        ast.UnaryOp,
        ast.IfExp,
        ast.Compare,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.And,
        ast.Or,
        ast.Not,
        ast.Gt,
        ast.GtE,
        ast.Lt,
        ast.LtE,
        ast.Eq,
        ast.NotEq,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Mod,
        ast.Pow,
        ast.USub,
    }

    def evaluate(self, expression: str, context: dict[str, Any]) -> bool:
        tree = ast.parse(expression, mode="eval")
        for node in ast.walk(tree):
            if type(node) not in self._allowed_nodes:  # noqa: E721
                raise UnsafeExpressionError(f"Unsupported expression node: {type(node).__name__}")
        return bool(self._eval_node(tree.body, context))

    def _eval_node(self, node: ast.AST, context: dict[str, Any]) -> Any:
        if isinstance(node, ast.Expression):
            return self._eval_node(node.body, context)
        if isinstance(node, ast.BoolOp):
            values = [self._eval_node(v, context) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
            raise UnsafeExpressionError("Unsupported boolean operator")
        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, context)
            right = self._eval_node(node.right, context)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                return left**right
            raise UnsafeExpressionError("Unsupported binary operator")
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand, context)
            if isinstance(node.op, ast.Not):
                return not operand
            if isinstance(node.op, ast.USub):
                return -operand
            raise UnsafeExpressionError("Unsupported unary operator")
        if isinstance(node, ast.IfExp):
            return self._eval_node(
                node.body if self._eval_node(node.test, context) else node.orelse, context
            )
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, context)
            result = True
            for operator, comparator in zip(node.ops, node.comparators, strict=False):
                right = self._eval_node(comparator, context)
                if isinstance(operator, ast.Gt):
                    result = result and left > right
                elif isinstance(operator, ast.GtE):
                    result = result and left >= right
                elif isinstance(operator, ast.Lt):
                    result = result and left < right
                elif isinstance(operator, ast.LtE):
                    result = result and left <= right
                elif isinstance(operator, ast.Eq):
                    result = result and left == right
                elif isinstance(operator, ast.NotEq):
                    result = result and left != right
                else:
                    raise UnsafeExpressionError("Unsupported comparison operator")
                left = right
            return result
        if isinstance(node, ast.Name):
            if node.id not in context:
                raise KeyError(f"Variable '{node.id}' is not available in context")
            return context[node.id]
        if isinstance(node, ast.Constant):
            return node.value
        raise UnsafeExpressionError(f"Unsupported expression node: {type(node).__name__}")
