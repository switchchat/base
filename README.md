# Project Demo

https://drive.google.com/file/d/1FgmdKnoRMTC26RCRIDpZuJl6nmJoJ_po/view?usp=share_link
(Google Drive Link)

# Cactus x Google DeepMind Hackathon

<div align="center">
  <img src="assets/banner.png" alt="Cactus x Google DeepMind" width="100%" />
</div>

## Context
- **Cactus** runs Google DeepMind's **FunctionGemma** at up to **3000 toks/sec** prefill speed on M4 Macs.
- While decode speed reaches **200 tokens/sec**, all without GPU, to remain energy-efficient.
- FunctionGemma is great at tool calling, but small models are not the smartest for some tasks.
- There is a need to dynamically combine **edge (local)** and **cloud (Gemini Flash)** to get the best of both worlds.
- Cactus develops various strategies for choosing when to fall back to Gemini or FunctionGemma.

## The Challenge
**Design a hybrid routing strategy that decides when to use the on-device model and when to fall back to the cloud.**

- **Goal**: Maximize correctness (F1 score) and on-device usage while minimizing latency.
- **Task**: Modify the `generate_hybrid` function in `main.py`.
- **Constraint**: Do **NOT** break the interface of `generate_hybrid`.
- **Scoring**: You will be objectively ranked on tool-call correctness (F1), speed, and edge/cloud ratio (prioritize local).

## Project Structure
- **`main.py`**: The core file where you will implement your strategy. Focus on the `generate_hybrid` function.
- **`benchmark.py`**: A local evaluation script. Run this to test your solution against various difficulty levels.
- **`submit.py`**: The script to submit your `main.py` to the global leaderboard.
- **`assets/`**: Contains project assets.

## Setup
Follow these steps to get started:

1.  **Fork & Clone**:
    ```bash
    git clone https://github.com/cactus-compute/cactus
    ```
2.  **Install Cactus**:
    ```bash
    cd cactus && source ./setup && cd ..
    cactus build --python
    ```
3.  **Download Model**:
    ```bash
    cactus download google/functiongemma-270m-it --reconvert
    ```
4.  **Authenticate Cactus**:
    - Get your key from the [Cactus Dashboard](https://cactuscompute.com/dashboard/api-keys).
    - Run:
      ```bash
      cactus auth
      ```
5.  **Install Dependencies**:
    ```bash
    pip install google-genai
    ```
6.  **Setup Gemini API**:
    - Get your key from [Google AI Studio](https://aistudio.google.com/api-keys).
    - Export it:
      ```bash
      export GEMINI_API_KEY="your-api-key-here"
      ```
7.  **Join the Community**:
    - Join the [Reddit channel](https://www.reddit.com/r/cactuscompute/) for technical questions.

## Workflow
1.  **Develop**: Open `main.py` and modify `generate_hybrid`. You can implement custom prompting, confidence scoring, or any logic to decide between local and cloud.
2.  **Test**: Run `python benchmark.py` to see how your strategy performs on local test cases.
    ```bash
    python benchmark.py
    ```
3.  **Submit**: When you are ready, submit your solution.
    ```bash
    python submit.py --team "YourTeamName" --location "YourCity"
    ```
    *Note: Submissions are limited to once every hour.*

## Scoring & Judging

### Quantitative Scoring (Leaderboard)
Your solution is scored based on:
1.  **F1 Score (50%)**: Accuracy of tool calls.
2.  **Time Score (25%)**: Speed (capped at 500ms baseline).
3.  **On-Device Ratio (25%)**: Higher usage of the local model is better.

### Qualitative Judging (Top 10)
The top 10 teams per location will be judged on:
- **Rubric 1**: Quality, depth, and cleverness of the hybrid routing algorithm.
- **Rubric 2**: End-to-end products that execute function calls to solve real-world problems.
- **Rubric 3**: Building low-latency voice-to-action products using `cactus_transcribe`.

## API Reference

### `cactus_init(model_path, corpus_dir=None)`
Initialize the model.

| Parameter | Type | Description |
|-----------|------|-------------|
| `model_path` | `str` | Path to model weights directory |
| `corpus_dir` | `str` | (Optional) dir of txt/md files for auto-RAG |

### `cactus_complete(model, messages, **options)`
Generate a completion.

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | handle | Model handle from `cactus_init` |
| `messages` | `list\|str` | List of message dicts or JSON string |
| `tools` | `list` | Optional tool definitions for function calling |
| `temperature` | `float` | Sampling temperature |
| `max_tokens` | `int` | Maximum tokens to generate |
| `force_tools` | `bool` | Constrain output to tool call format |
| `confidence_threshold` | `float` | Minimum confidence for local generation |

**Response format**:
```json
{
    "success": true,
    "response": "Hello!",
    "function_calls": [],
    "confidence": 0.85,
    "time_to_first_token_ms": 45.2,
    "total_time_ms": 163.7
}
```

### `cactus_transcribe(model, audio_path, prompt="")`
Transcribe audio using Whisper.

### `cactus_embed(model, text, normalize=False)`
Generate embeddings for text.

### `cactus_reset(model)`
Reset model state (clear KV cache).

### `cactus_destroy(model)`
Free model memory. Always call this when done.

---
**Resources**:
- [Leaderboard](https://cactusevals.ngrok.app)
- [Cactus Dashboard](https://cactuscompute.com/dashboard/api-keys)
