# Project Description

Current voice assistants (Siri, Google Assistant) operate on a rigid, one-shot model. They excel at simple queries but fail when faced with multi-step instructions. If you ask Siri to "Book a dinner for two at that Italian place we liked last month and send the address to my wife," it breaks down because it cannot handle context, memory, and sequential tool execution simultaneously. 

Our solution bridges this gap by using a voice automation agentic workflow to **break down complex, natural-language requests into actionable, sequential steps. By leveraging an intelligent hybrid routing engine—combining the blazing-fast, on-device execution of FunctionGemma via Cactus with the advanced reasoning capabilities of cloud-based Gemini—our assistant maintains context, accesses memory, and dynamically orchestrates multiple tools.**

## Key Features
* **Agentic Routine Execution:** Instead of one-off commands, our system handles comprehensive, multi-step workflows (like `morning_prep`, `workout`, and `evening_wind-down`) autonomously.
* **Dynamic Tool Registry:** The agent intelligently selects and sequences the right simulated tools from its registry to accomplish the entire task without requiring constant user prompting.
* **Hybrid Edge/Cloud Routing:** To maximize speed and privacy while maintaining high accuracy, our engine dynamically decides when to process tool calls locally on-device (FunctionGemma) and when to fall back to the cloud (Gemini) for more complex reasoning.
* **Contextual Memory:** The workflow retains context across interactions, allowing it to remember preferences (like "that Italian place we liked last month") and chain actions together seamlessly.
