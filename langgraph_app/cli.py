from langgraph_app.graphs.conversation_graph import create_conversation_graph
from langgraph_app.state import ConversationState


def main():
    graph = create_conversation_graph()

    print("=== EmotionalRole-RAG / LangGraph CLI ===")
    print("输入你的问题，输入 quit/exit 退出。")

    while True:
        query = input("\n你：").strip()
        if not query:
            continue
        if query.lower() in {"quit", "exit", "q"}:
            break

        state: ConversationState = {
            "user_query": query,
            "selected_character": "支持者",   # 你可以换成具体角色名
            "history": [],
        }
        result = graph.invoke(state)
        answer = result.get("final_answer", "")
        character = result.get("selected_character", "支持者")

        print(f"\n{character}：{answer}")


if __name__ == "__main__":
    main()