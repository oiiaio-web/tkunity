# -*- coding: utf-8 -*-
"""脚本子集编译器：把 Script 组件里的 Python 片段编译成可跨平台执行的小型 AST。

桌面预览用完整的 ``exec`` 执行脚本；导出 APK 时没有 Python 解释器，于是这里把
脚本编译成一份 JSON AST，由 ``GameView.java`` 里的 ``ScriptVM`` 解释执行 ——
两边支持同一套语法，行为保持一致。

支持的语法（有意保持精简，覆盖绝大多数 2D 玩法）::

    数字 / 字符串 / True / False / None
    + - * / // % **            一元 + - not
    == != < <= > >=  is / is not
    and / or
    赋值  x = 1   增强赋值  x += 1
    if / elif / else
    while（带迭代上限）
    for i in range(...)（1~3 个参数）
    break / continue / pass
    调用：log / find / spawn / destroy / restart / abs / min / max / round /
          int / float / str / len / math.sin / math.cos / math.tan / math.sqrt /
          math.atan2 / math.hypot / math.fabs / math.pi / math.e

不支持的写法（导入、函数定义、类、列表推导、下标、任意属性访问等）会抛出
``ScriptError``，导出时该钩子会被跳过并在 ``validate`` 里提示。
"""
from __future__ import annotations

import ast
import math

__all__ = [
    "ScriptError", "compile_script", "compile_project", "evaluate",
    "SUPPORTED_FUNCS", "SUPPORTED_MATH", "SUPPORTED_NAMES",
]

# 宿主函数（桌面运行时与 Java ScriptVM 都必须实现同名语义）
SUPPORTED_FUNCS = [
    "log", "find", "spawn", "destroy", "restart",
    "abs", "min", "max", "round", "int", "float", "str", "len",
]
# math.* 白名单
SUPPORTED_MATH = ["sin", "cos", "tan", "sqrt", "atan2", "hypot", "fabs", "pi", "e"]

# 宿主提供的变量（可读，部分可写）
SUPPORTED_NAMES = [
    "x", "y", "width", "height", "w", "h",
    "vx", "vy", "rotation", "scale", "dt", "time", "other", "name", "tag",
]

_BINOPS = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
    ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**",
}
_CMPOPS = {
    ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=",
    ast.Gt: ">", ast.GtE: ">=", ast.Is: "is", ast.IsNot: "is not",
    ast.In: None, ast.NotIn: None,
}
_AUG = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
    ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**",
}


class ScriptError(Exception):
    """脚本里出现了 APK 运行时不支持的语法。"""


class _Compiler(object):
    def __init__(self, filename="<script>"):
        self.filename = filename
        self.local_names = set()

    # ---------------- 语句 ----------------
    def block(self, body):
        return [self.stmt(node) for node in body]

    def stmt(self, node):
        if isinstance(node, ast.Assign):
            return self.assign(node)
        if isinstance(node, ast.AugAssign):
            return self.aug_assign(node)
        if isinstance(node, ast.If):
            return {
                "t": "if",
                "c": self.expr(node.test),
                "then": self.block(node.body),
                "else": self.block(node.orelse),
            }
        if isinstance(node, ast.While):
            return {
                "t": "while",
                "c": self.expr(node.test),
                "body": self.block(node.body),
                "else": self.block(node.orelse),
            }
        if isinstance(node, ast.For):
            return self.for_(node)
        if isinstance(node, ast.Expr):
            if not isinstance(node.value, ast.Call):
                raise self._err(node, "只支持函数调用作为独立语句")
            return {"t": "expr", "e": self.expr(node.value)}
        if isinstance(node, ast.Pass):
            return {"t": "pass"}
        if isinstance(node, ast.Break):
            return {"t": "break"}
        if isinstance(node, ast.Continue):
            return {"t": "continue"}
        raise self._err(node, "不支持的语句: %s" % type(node).__name__)

    def assign(self, node):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            raise self._err(node, "只支持给单个变量赋值（x = ...）")
        name = node.targets[0].id
        self.local_names.add(name)
        return {"t": "assign", "name": name, "op": "=", "e": self.expr(node.value)}

    def aug_assign(self, node):
        if not isinstance(node.target, ast.Name):
            raise self._err(node, "增强赋值只支持变量")
        op = _AUG.get(type(node.op))
        if op is None:
            raise self._err(node, "不支持的运算符")
        name = node.target.id
        self.local_names.add(name)
        return {"t": "assign", "name": name, "op": op, "e": self.expr(node.value)}

    def for_(self, node):
        if not isinstance(node.target, ast.Name):
            raise self._err(node, "for 只能遍历单个变量")
        if not (isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name)
                and node.iter.func.id == "range"):
            raise self._err(node, "for 只支持 range(...)")
        args = [self.expr(a) for a in node.iter.args]
        if not 1 <= len(args) <= 3:
            raise self._err(node, "range() 需要 1~3 个参数")
        self.local_names.add(node.target.id)
        return {
            "t": "for",
            "var": node.target.id,
            "args": args,
            "body": self.block(node.body),
            "else": self.block(node.orelse),
        }

    # ---------------- 表达式 ----------------
    def expr(self, node):
        if isinstance(node, ast.Constant):
            return self.constant(node)
        if isinstance(node, ast.Name):
            return {"t": "name", "v": node.id}
        if isinstance(node, ast.BinOp):
            op = _BINOPS.get(type(node.op))
            if op is None:
                raise self._err(node, "不支持的运算符")
            return {"t": "bin", "op": op, "a": self.expr(node.left), "b": self.expr(node.right)}
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                return {"t": "un", "op": "-", "a": self.expr(node.operand)}
            if isinstance(node.op, ast.UAdd):
                return self.expr(node.operand)
            if isinstance(node.op, ast.Not):
                return {"t": "un", "op": "not", "a": self.expr(node.operand)}
            raise self._err(node, "不支持的一元运算符")
        if isinstance(node, ast.BoolOp):
            op = "and" if isinstance(node.op, ast.And) else "or"
            return {"t": "bool", "op": op, "a": self.expr(node.values[0]),
                    "b": self.expr(node.values[1])}
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1:
                raise self._err(node, "链式比较请拆成多个条件")
            op = _CMPOPS.get(type(node.ops[0]))
            if op is None:
                raise self._err(node, "不支持的比较运算符（in 不可用）")
            return {"t": "cmp", "op": op,
                    "a": self.expr(node.left), "b": self.expr(node.comparators[0])}
        if isinstance(node, ast.Call):
            return self.call(node)
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "math":
                if node.attr not in SUPPORTED_MATH:
                    raise self._err(node, "math.%s 不在白名单" % node.attr)
                return {"t": "call", "fn": "math." + node.attr, "args": []}
            raise self._err(node, "只允许访问 math.*")
        if isinstance(node, ast.IfExp):
            return {
                "t": "ifexp", "c": self.expr(node.test),
                "a": self.expr(node.body), "b": self.expr(node.orelse),
            }
        raise self._err(node, "不支持的表达式: %s" % type(node).__name__)

    def constant(self, node):
        value = node.value
        if isinstance(value, bool):
            return {"t": "const", "v": value}
        if value is None:
            return {"t": "none"}
        if isinstance(value, (int, float)):
            return {"t": "num", "v": float(value)}
        if isinstance(value, str):
            return {"t": "str", "v": value}
        raise self._err(node, "只支持数字 / 字符串 / True / False / None 常量")

    def call(self, node):
        fn = None
        if isinstance(node.func, ast.Name):
            fn = node.func.id
            if fn not in SUPPORTED_FUNCS:
                raise self._err(node, "函数 %s 不在白名单" % fn)
        elif isinstance(node.func, ast.Attribute):
            if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "math"):
                raise self._err(node, "只允许调用 math.*")
            if node.func.attr not in SUPPORTED_MATH:
                raise self._err(node, "math.%s 不在白名单" % node.func.attr)
            fn = "math." + node.func.attr
        else:
            raise self._err(node, "不支持这种函数调用")
        if node.keywords:
            raise self._err(node, "不支持关键字参数")
        return {"t": "call", "fn": fn, "args": [self.expr(a) for a in node.args]}

    def _err(self, node, message):
        line = getattr(node, "lineno", "?")
        return ScriptError("%s（第 %s 行）" % (message, line))


def compile_script(code, filename="<script>"):
    """把一段脚本编译成 JSON AST（dict）。语法不支持时抛 ScriptError。"""
    text = (code or "").strip()
    if not text:
        return None
    try:
        tree = ast.parse(text, mode="exec")
    except SyntaxError as exc:
        raise ScriptError("语法错误: %s（第 %s 行）" % (exc.msg, exc.lineno))
    compiler = _Compiler(filename)
    program = {"stmts": compiler.block(tree.body), "vars": sorted(compiler.local_names)}
    return program


def compile_project(project):
    """编译项目里所有 Script 组件。

    返回 ``(programs, warnings)``：
        programs: {"<entity id>": {"on_start": prog, ...}}
        warnings: ["物体名.on_update: 不支持的语法 ...", ...]
    """
    programs = {}
    warnings = []
    for entity in project.get("entities", []):
        script = entity.get("components", {}).get("Script")
        if not script:
            continue
        hooks = {}
        for hook in ("on_start", "on_update", "on_tap", "on_collision", "on_destroy"):
            code = script.get(hook) or ""
            if not code.strip():
                continue
            try:
                prog = compile_script(code)
            except ScriptError as exc:
                warnings.append("%s.%s: %s" % (entity.get("name", "?"), hook, exc))
                continue
            if prog is not None:
                hooks[hook] = prog
        if hooks:
            programs[str(entity.get("id"))] = hooks
    return programs, warnings


# ---------------------------------------------------------------- 参考求值器
class _Break(Exception):
    pass


class _Continue(Exception):
    pass


def _truth(value):
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return len(value) > 0
    return True


def _to_number(value):
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise ScriptError("无法转成数字: %r" % (value,))


def _binop(op, a, b):
    if op == "+" and (isinstance(a, str) or isinstance(b, str)):
        return _to_str(a) + _to_str(b)
    num_a, num_b = _to_number(a), _to_number(b)
    if op == "+":
        return num_a + num_b
    if op == "-":
        return num_a - num_b
    if op == "*":
        return num_a * num_b
    if op == "/":
        return num_a / num_b
    if op == "//":
        return math.floor(num_a / num_b)
    if op == "%":
        return num_a % num_b
    if op == "**":
        return num_a ** num_b
    raise ScriptError("未知运算符 %s" % op)


def _to_str(value):
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def evaluate(program, env, host=None, max_steps=200000):
    """参考实现：在 ``env`` 字典上执行编译后的程序（测试与 validate 用）。

    host 需要提供 call(fn, args) / log(msg) / find(name) / spawn(...) 等；
    默认 host 只实现数学函数与 log 打印。
    """
    state = {"steps": 0}
    if host is None:
        host = _DefaultHost()
    vm = _Eval(env, host, state, max_steps)
    vm.execute(program.get("stmts", []))
    return env


class _DefaultHost(object):
    def call(self, fn, args):
        if fn == "log":
            print("[script]", *args)
            return None
        if fn == "find":
            return None
        if fn == "spawn":
            return None
        if fn == "destroy":
            return None
        if fn == "restart":
            return None
        import builtins
        if fn in ("abs", "min", "max", "round", "int", "float", "str", "len"):
            return getattr(builtins, fn)(*[_pyval(a) for a in args])
        if fn.startswith("math."):
            name = fn.split(".", 1)[1]
            if name == "pi":
                return math.pi
            if name == "e":
                return math.e
            return getattr(math, name)(*[_to_number(a) for a in args])
        raise ScriptError("未实现的函数: %s" % fn)


def _pyval(value):
    if value is None:
        return None
    return value


class _Eval(object):
    def __init__(self, env, host, state, max_steps):
        self.env = env
        self.host = host
        self.state = state
        self.max_steps = max_steps

    def _step(self):
        self.state["steps"] += 1
        if self.state["steps"] > self.max_steps:
            raise ScriptError("脚本执行步数超限（可能有死循环）")

    def execute(self, body):
        for node in body:
            self.stmt(node)

    def stmt(self, node):
        self._step()
        kind = node["t"]
        if kind == "assign":
            value = self.eval(node["e"])
            if node["op"] != "=":
                value = _binop(node["op"], self.lookup(node["name"]), value)
            self.env[node["name"]] = value
            return
        if kind == "if":
            if _truth(self.eval(node["c"])):
                self.execute(node["then"])
            else:
                self.execute(node.get("else", []))
            return
        if kind == "while":
            while _truth(self.eval(node["c"])):
                self._step()
                try:
                    self.execute(node["body"])
                except _Break:
                    break
                except _Continue:
                    continue
            else:
                self.execute(node.get("else", []))
            return
        if kind == "for":
            args = [_to_number(self.eval(a)) for a in node["args"]]
            if len(args) == 1:
                start, stop, step = 0.0, args[0], 1.0
            elif len(args) == 2:
                start, stop, step = args[0], args[1], 1.0
            else:
                start, stop, step = args
            value = start
            while (step > 0 and value < stop) or (step < 0 and value > stop):
                self._step()
                self.env[node["var"]] = value
                try:
                    self.execute(node["body"])
                except _Break:
                    break
                except _Continue:
                    pass
                value += step
            return
        if kind == "expr":
            self.eval(node["e"])
            return
        if kind == "pass":
            return
        if kind == "break":
            raise _Break()
        if kind == "continue":
            raise _Continue()
        raise ScriptError("未知语句 %r" % kind)

    def lookup(self, name):
        if name in self.env:
            return self.env[name]
        return None

    def eval(self, node):
        kind = node["t"]
        if kind == "num":
            return node["v"]
        if kind == "str":
            return node["v"]
        if kind == "const":
            return node["v"]
        if kind == "none":
            return None
        if kind == "name":
            name = node["v"]
            if name in self.env:
                return self.env[name]
            raise ScriptError("未知变量: %s" % name)
        if kind == "bin":
            return _binop(node["op"], self.eval(node["a"]), self.eval(node["b"]))
        if kind == "un":
            value = self.eval(node["a"])
            if node["op"] == "-":
                return -_to_number(value)
            return not _truth(value)
        if kind == "bool":
            left = self.eval(node["a"])
            if node["op"] == "and":
                return self.eval(node["b"]) if _truth(left) else left
            return left if _truth(left) else self.eval(node["b"])
        if kind == "cmp":
            return self.compare(node["op"], self.eval(node["a"]), self.eval(node["b"]))
        if kind == "call":
            return self.host.call(node["fn"], [self.eval(a) for a in node["args"]])
        if kind == "ifexp":
            return self.eval(node["a"]) if _truth(self.eval(node["c"])) else self.eval(node["b"])
        raise ScriptError("未知表达式 %r" % kind)

    @staticmethod
    def compare(op, a, b):
        if op == "==":
            return a == b
        if op == "!=":
            return a != b
        if op == "is":
            if a is None or b is None:
                return a is b
            return a == b
        if op == "is not":
            if a is None or b is None:
                return a is not b
            return a != b
        if isinstance(a, str) and isinstance(b, str):
            return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
        left, right = _to_number(a), _to_number(b)
        return {"<": left < right, "<=": left <= right,
                ">": left > right, ">=": left >= right}[op]
