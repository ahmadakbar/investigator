from deepagents import create_deep_agent

from investigator.tools.agent_tools import make_tools
from investigator.transaction_deck import load_transactions


def main ():
    csv_path = "/Users/akbarahmad2/work/My/harness/Investigator/investigator/data/demo/synthetic_personal_spending.csv"
    with load_transactions(csv_path) as deck:

        system_prompt=(
            "Investigate the dataset using the provided analysis tools. "
            "Base numerical claims on tool results. "
            "Keep currencies separate. "
            "State the date range and explain relevant exclusions."
        )
        agent = create_deep_agent(
            model="openai:gpt-5.5",
            tools=make_tools(deck),
            system_prompt= system_prompt
        )
        result = agent.invoke({
            "messages": [{
                "role": "user",
                "content": "How much did I spend in April 2026?"
            }]
        })

    for message in result["messages"]:
        for call in getattr(message, "tool_calls", []):
            print(call["name"], call["args"])

    print(result["messages"][-1].content)

if __name__ == "__main__":
    main()