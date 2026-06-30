# Jarvis

A voice assistant Alexa skill backed by a swappable LLM (via [litellm](https://docs.litellm.ai/)), web search, and a personal S3-backed wiki the assistant can read from and write to across sessions.

## Prerequisites

- AWS account (Lambda + S3)
- Amazon Alexa developer account
- An API key for an LLM provider supported by litellm (Groq, OpenAI, Anthropic, Gemini, ...)
- A [Tavily](https://tavily.com) API key (used for web search)
- Python 3.12, AWS CLI configured (`aws configure`)

## Setup

1. Clone the repo and `cd jarvis`
2. `pip install -r requirements.txt -r requirements-dev.txt`
3. Copy `.env.example` to `.env` and fill in:
   - `LLM_MODEL` — provider/model string, e.g. `groq/openai/gpt-oss-20b` (see table below)
   - the matching provider API key env var
   - `TAVILY_API_KEY`
   - `S3_BUCKET_NAME` — S3 bucket used to store the per-user wiki

## Choosing a provider

`LLM_MODEL` uses litellm's `provider/model` naming. litellm reads the matching API key env var automatically based on the prefix:

| `LLM_MODEL` example | Required env var |
|---|---|
| `groq/openai/gpt-oss-20b` | `GROQ_API_KEY` |
| `openai/gpt-4o-mini` | `OPENAI_API_KEY` |
| `anthropic/claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| `gemini/gemini-2.0-flash` | `GEMINI_API_KEY` |

Full provider list: https://docs.litellm.ai/docs/providers. Pick a model that supports tool/function calling — Jarvis relies on it for web search and wiki lookups.

## Running tests

```bash
pytest
```

## Deploying

```bash
python scripts/deploy.py
# or
bash scripts/deploy.sh
```

Both install dependencies into `package/`, zip the source into `lambda.zip`, and upload it to an existing Lambda function named `jarvis` (set `REGION`/`FUNCTION_NAME` at the top of the script if yours differ). The Lambda function must already exist with its env vars (`LLM_MODEL`, the provider key, `TAVILY_API_KEY`, `S3_BUCKET_NAME`) configured in the AWS console.

## Setting up the Alexa skill

1. Install the [ASK CLI](https://developer.amazon.com/en-US/docs/alexa/smapi/quick-start-alexa-skills-kit-command-line-interface.html) or use the [Alexa developer console](https://developer.amazon.com/alexa/console/ask)
2. Create a new custom skill and import the manifest + interaction model from `skill-package/`
3. Point the skill's endpoint at your deployed Lambda function's ARN
4. Build the model and test in the simulator: "Alexa, open Jarvis"
