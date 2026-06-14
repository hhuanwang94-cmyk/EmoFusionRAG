from typing import Callable, Dict, Any, Type


class _EndType:
    """表示图执行结束的特殊标记"""
    pass


END = _EndType()


class CompiledGraph:
    """
    编译后的图执行器：
    - 只有一个方法 invoke(state) -> state
    """

    def __init__(self, nodes: Dict[str, Callable[[Any], Any]],
                 edges: Dict[str, Any],
                 entry_point: str):
        self.nodes = nodes
        self.edges = edges
        self.entry_point = entry_point

    def invoke(self, state: Any) -> Any:
        """
        从入口节点开始，依次按 edges 串起来执行每个节点函数。
        每个节点接收并返回同一个 state。
        """
        current = self.entry_point

        while True:
            node_fn = self.nodes.get(current)
            if node_fn is None:
                raise RuntimeError(f"Node '{current}' not found in graph.")

            state = node_fn(state)

            next_node = self.edges.get(current, END)
            if next_node is END:
                break
            current = next_node

        return state


class StateGraph:
    """
    简化版 StateGraph，模仿 langgraph.graph.StateGraph 的基本用法：
    - add_node(name, fn)
    - add_edge(src, dst)
    - set_entry_point(name)
    - compile() -> CompiledGraph
    """

    def __init__(self, state_type: Type[Any] = dict):
        self.state_type = state_type
        self._nodes: Dict[str, Callable[[Any], Any]] = {}
        self._edges: Dict[str, Any] = {}
        self._entry_point: str | None = None

    def add_node(self, name: str, fn: Callable[[Any], Any]):
        if name in self._nodes:
            raise ValueError(f"Node '{name}' already exists.")
        self._nodes[name] = fn

    def add_edge(self, src: str, dst: Any):
        """
        dst 可以是另一个节点名，也可以是 END
        """
        if src not in self._nodes:
            raise ValueError(f"Source node '{src}' not found when adding edge.")
        self._edges[src] = dst

    def set_entry_point(self, name: str):
        if name not in self._nodes:
            raise ValueError(f"Entry point node '{name}' not found.")
        self._entry_point = name

    def compile(self) -> CompiledGraph:
        if self._entry_point is None:
            raise RuntimeError("Entry point not set.")
        return CompiledGraph(self._nodes, self._edges, self._entry_point)